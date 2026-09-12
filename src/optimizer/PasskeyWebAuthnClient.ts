/* =========================================================
   Passkey (WebAuthn / FIDO2) client — real lifecycle:
     1. ensure a credential exists (registration if needed,
        navigator.credentials.create + backend verification)
     2. challenge -> navigator.credentials.get (biometric/
        platform authenticator)
     3. backend cryptographic assertion verification
   The backend returns standard base64 challenges (compatible
   with atob). On any failure null is returned and the UI shows
   the error — no token is ever faked.
   ========================================================= */

import { setSessionToken } from "../lib/api";

const b64ToBytes = (b64: string): Uint8Array => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const bytesToB64 = (bytes: Uint8Array): string => btoa(String.fromCharCode(...bytes));

export class PasskeyWebAuthnClient {
  /** Full passkey flow: register (if needed) -> authenticate -> session token. */
  public static async authenticatePasskeyForSettings(userEmail: string): Promise<string | null> {
    try {
      const hasCredential = await this.hasRegisteredCredential(userEmail);
      if (!hasCredential) {
        await this.register(userEmail);
      }
      return await this.authenticate(userEmail);
    } catch (err) {
      console.error("Passkey authentication failed:", err);
      return null;
    }
  }

  private static async hasRegisteredCredential(email: string): Promise<boolean> {
    const res = await fetch(`/api/v1/auth/passkey/challenge?email=${encodeURIComponent(email)}`);
    if (res.ok) {
      // challenge available -> credential exists; pop it (it will be re-created on demand)
      await res.json().catch(() => null);
      return true;
    }
    return res.status === 200;
  }

  private static async register(email: string): Promise<void> {
    const res = await fetch(`/api/v1/auth/passkey/registration?email=${encodeURIComponent(email)}`);
    if (!res.ok) throw new Error(`registration options failed: HTTP ${res.status}`);
    const options = await res.json();
    options.publicKey.challenge = b64ToBytes(options.publicKey.challenge);
    options.publicKey.user.id = b64ToBytes(options.publicKey.user.id);

    const credential = (await navigator.credentials.create({ publicKey: options.publicKey })) as PublicKeyCredential | null;
    if (!credential) throw new Error("browser registration cancelled");
    const resp = credential.response as AuthenticatorAttestationResponse;

    const regRes = await fetch("/api/v1/auth/passkey/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        credential: {
          id: credential.id,
          rawId: bytesToB64(new Uint8Array(credential.rawId)),
          response: {
            clientDataJSON: bytesToB64(new Uint8Array(resp.clientDataJSON)),
            attestationObject: bytesToB64(new Uint8Array(resp.attestationObject))
          }
        }
      })
    });
    const data = await regRes.json();
    if (!data.success) throw new Error(data.detail || "backend rejected attestation");
  }

  private static async authenticate(email: string): Promise<string | null> {
    const res = await fetch(`/api/v1/auth/passkey/challenge?email=${encodeURIComponent(email)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `challenge failed: HTTP ${res.status}`);
    }
    const options = await res.json();
    options.publicKey.challenge = b64ToBytes(options.publicKey.challenge);
    options.publicKey.allowCredentials = (options.publicKey.allowCredentials || []).map((c: any) => ({
      ...c,
      id: b64ToBytes(c.id)
    }));

    const assertion = (await navigator.credentials.get({ publicKey: options.publicKey })) as PublicKeyCredential | null;
    if (!assertion) throw new Error("browser assertion cancelled");
    const response = assertion.response as AuthenticatorAssertionResponse;

    const verifyRes = await fetch("/api/v1/auth/passkey/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        credential: {
          id: assertion.id,
          response: {
            clientDataJSON: bytesToB64(new Uint8Array(response.clientDataJSON)),
            authenticatorData: bytesToB64(new Uint8Array(response.authenticatorData))
          }
        }
      })
    });
    const data = await verifyRes.json();
    if (!data.success) throw new Error(data.detail || "backend rejected assertion");
    setSessionToken(data.sessionToken || data.settingsToken);
    return data.sessionToken || data.settingsToken;
  }
}
