const gmailButton = document.getElementById('gmailLogin');
const guestLink = document.querySelector('[data-guest-login]');

const OAUTH_SCOPES = [
  'openid',
  'email',
  'profile',
];

const getGoogleClientId = () => {
  const metaClient = document.querySelector('meta[name="google-client-id"]');
  if (metaClient?.content) return metaClient.content.trim();

  if (window.GOOGLE_CLIENT_ID) return window.GOOGLE_CLIENT_ID;

  if (gmailButton?.dataset.googleClientId) return gmailButton.dataset.googleClientId.trim();

  return '';
};

const loadGoogleScript = () =>
  new Promise((resolve, reject) => {
    if (window.google?.accounts?.oauth2) {
      resolve();
      return;
    }

    const existing = document.querySelector('script[data-google-sdk]');
    if (existing) {
      existing.addEventListener('load', resolve, { once: true });
      existing.addEventListener('error', reject, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.dataset.googleSdk = 'true';
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });

const buildRedirectUri = () => {
  try {
    const redirect = new URL('map.html', window.location.href);
    return redirect.toString();
  } catch (error) {
    return `${window.location.origin}/map.html`;
  }
};

const startGoogleLogin = async () => {
  if (!gmailButton) return;

  const clientId = getGoogleClientId();
  const redirectUri = buildRedirectUri();

  gmailButton.classList.add('loading');
  gmailButton.textContent = 'Connecting to Google…';

  if (!clientId) {
    // Fallback: send the user to Google's hosted sign-in page.
    window.location.href = `https://accounts.google.com/signin/v2/identifier?continue=${encodeURIComponent(redirectUri)}`;
    return;
  }

  try {
    await loadGoogleScript();

    const codeClient = window.google.accounts.oauth2.initCodeClient({
      client_id: clientId,
      scope: OAUTH_SCOPES.join(' '),
      ux_mode: 'redirect',
      redirect_uri: redirectUri,
    });

    codeClient.requestCode();
  } catch (error) {
    console.error('Google Sign-In failed to initialize', error);
    window.location.href = `https://accounts.google.com/signin/v2/identifier?continue=${encodeURIComponent(redirectUri)}`;
  }
};

if (gmailButton) {
  gmailButton.addEventListener('click', startGoogleLogin);
}

if (guestLink) {
  guestLink.addEventListener('click', () => {
    guestLink.classList.add('loading');
  });
}
