const base64UrlToArrayBuffer = (value: string): ArrayBuffer => {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }
  return bytes.buffer;
};

const uint8ArrayToBase64Url = (value: Uint8Array): string => {
  let binary = '';
  for (let i = 0; i < value.length; i += 1) {
    binary += String.fromCharCode(value[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

const arrayBufferToBase64Url = (value: ArrayBuffer): string => {
  return uint8ArrayToBase64Url(new Uint8Array(value));
};

const credentialToJSON = (credential: PublicKeyCredential): Record<string, any> => {
  const response = credential.response;
  const authenticatorAttachment =
    "authenticatorAttachment" in credential
      ? credential.authenticatorAttachment
      : null;
  const output: Record<string, any> = {
    id: credential.id,
    rawId: arrayBufferToBase64Url(credential.rawId),
    type: credential.type,
    response: {},
  };

  if (authenticatorAttachment) {
    output.authenticatorAttachment = authenticatorAttachment;
  }

  if (response instanceof AuthenticatorAttestationResponse) {
    const transports =
      typeof response.getTransports === 'function' ? response.getTransports() : [];

    output.response = {
      clientDataJSON: arrayBufferToBase64Url(response.clientDataJSON),
      attestationObject: arrayBufferToBase64Url(response.attestationObject),
    };

    if (Array.isArray(transports) && transports.length > 0) {
      output.response.transports = transports;
      output.transports = transports;
    }
  } else if (response instanceof AuthenticatorAssertionResponse) {
    output.response = {
      clientDataJSON: arrayBufferToBase64Url(response.clientDataJSON),
      authenticatorData: arrayBufferToBase64Url(response.authenticatorData),
      signature: arrayBufferToBase64Url(response.signature),
      userHandle: response.userHandle ? arrayBufferToBase64Url(response.userHandle) : null,
    };
  }

  return output;
};

export const browserSupportsPasskeys = (): boolean => {
  return typeof window !== 'undefined' && typeof window.PublicKeyCredential !== 'undefined';
};

export const createPasskeyCredential = async (options: Record<string, any>): Promise<Record<string, any>> => {
  const publicKey = {
    ...options,
    challenge: base64UrlToArrayBuffer(options.challenge),
    user: {
      ...options.user,
      id: base64UrlToArrayBuffer(options.user.id),
    },
    excludeCredentials: (options.excludeCredentials || []).map((item: any) => ({
      ...item,
      id: base64UrlToArrayBuffer(item.id),
    })),
  } as PublicKeyCredentialCreationOptions;

  const credential = await navigator.credentials.create({ publicKey });
  if (!credential || !(credential instanceof PublicKeyCredential)) {
    throw new Error('Passkey registration was cancelled.');
  }

  return credentialToJSON(credential);
};

export const getPasskeyAssertion = async (options: Record<string, any>): Promise<Record<string, any>> => {
  const publicKey = {
    ...options,
    challenge: base64UrlToArrayBuffer(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((item: any) => ({
      ...item,
      id: base64UrlToArrayBuffer(item.id),
    })),
  } as PublicKeyCredentialRequestOptions;

  const credential = await navigator.credentials.get({ publicKey });
  if (!credential || !(credential instanceof PublicKeyCredential)) {
    throw new Error('Passkey authentication was cancelled.');
  }

  return credentialToJSON(credential);
};
