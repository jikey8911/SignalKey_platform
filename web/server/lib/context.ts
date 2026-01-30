import type { CreateExpressContextOptions } from "@trpc/server/adapters/express";
import { COOKIE_NAME } from "@shared/const";
import { verifySession } from "./jwt";
import { User } from "../mongodb";

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

        // Get user from MongoDB
        const mongoUser = await User.findOne({ openId: session.openId });
        if (!mongoUser) {
            return { req: opts.req, res: opts.res, user: null };
        }

        user = {
            openId: mongoUser.openId,
            name: mongoUser.name,
            email: mongoUser.email,
            role: mongoUser.role,
        };
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
