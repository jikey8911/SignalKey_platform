import jwt from 'jsonwebtoken';

export interface SessionPayload {
    openId: string;
    appId: string;
    name: string;
}

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
console.log(`[JWT] Secret prefix: ${JWT_SECRET.substring(0, 4)}... (len: ${JWT_SECRET.length})`);
const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;

/**
 * Generate a JWT token for a user session
 */
export function signSession(payload: SessionPayload, expiresInMs: number = ONE_YEAR_MS): string {
    return jwt.sign(payload, JWT_SECRET, {
        expiresIn: `${Math.floor(expiresInMs / 1000)}s`,
    });
}

/**
 * Verify and decode a JWT token
 */
export function verifySession(token: string): SessionPayload | null {
    try {
        const decoded = jwt.verify(token, JWT_SECRET) as SessionPayload;
        return decoded;
    } catch (error) {
        console.error('[JWT] Verification failed:', error);
        return null;
    }
}
