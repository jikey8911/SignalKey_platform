import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router, protectedProcedure } from "./_core/trpc";
import { z } from "zod";

export const appRouter = router({
    // if you need to use socket.io, read and register route in server/_core/index.ts, all api should start with '/api/' so that the gateway can route correctly
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(opts => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),

  trading: router({
    getConfig: protectedProcedure.query(async ({ ctx }) => {
      const { getAppConfig } = await import("./db");
      return await getAppConfig(ctx.user.id);
    }),
    updateConfig: protectedProcedure
      .input(z.record(z.string(), z.any()))
      .mutation(async ({ ctx, input }) => {
        const { upsertAppConfig } = await import("./db");
        await upsertAppConfig(ctx.user.id, input);
        return { success: true };
      }),
    getSignals: protectedProcedure.query(async ({ ctx }) => {
      const { getTradingSignals } = await import("./db");
      return await getTradingSignals(ctx.user.id);
    }),
    getTrades: protectedProcedure.query(async ({ ctx }) => {
      const { getTrades } = await import("./db");
      return await getTrades(ctx.user.id);
    }),
    getBalances: protectedProcedure.query(async ({ ctx }) => {
      const { getVirtualBalances } = await import("./db");
      return await getVirtualBalances(ctx.user.id);
    }),
  }),
});

export type AppRouter = typeof appRouter;
