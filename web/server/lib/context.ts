import type { CreateExpressContextOptions } from "@trpc/server/adapters/express";
import { COOKIE_NAME } from "@shared/const";
import { verifySession } from "./jwt";

const BACKEND_API_URL = process.env.INTERNAL_API_URL || process.env.BACKEND_API_URL || "http://localhost:8000";

export type TrpcContext = {
    req: CreateExpressContextOptions["req"];
    res: CreateExpressContextOptions["res"];
    user: any | null;
};

export async function createContext(
    opts: CreateExpressContextOptions
): Promise<TrpcContext> {
    let user: any | null = null;

    try {
        // Get cookie from request
        const cookieHeader = opts.req.headers.cookie;
        if (!cookieHeader) {
            return { req: opts.req, res: opts.res, user: null };
        }

        // Parse cookies
        const cookies = cookieHeader.split(';').reduce((acc, cookie) => {
            const [key, value] = cookie.trim().split('=');
            acc[key] = value;
            return acc;
        }, {} as Record<string, string>);

        const token = cookies[COOKIE_NAME];
        if (!token) {
            return { req: opts.req, res: opts.res, user: null };
        }

        // Verify JWT token
        const session = verifySession(token);
        if (!session) {
            return { req: opts.req, res: opts.res, user: null };
        }

        // Get user from backend API instead of MongoDB
        try {
            const response = await fetch(`${BACKEND_API_URL}/auth/me`, {
                headers: {
                    'Cookie': `manus.sid=${token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                user = data.user;
            }
        } catch (apiError) {
            console.error('[Context] Error fetching user from backend API:', apiError);
            // Fallback to session data if backend is unavailable
            user = {
                openId: session.openId,
                name: session.name || session.openId,
                email: null,
                role: 'user',
            };
        }
    } catch (error) {
        console.error('[Context] Authentication error:', error);
        user = null;
    }

    return {
        req: opts.req,
        res: opts.res,
        user,
    };
}
