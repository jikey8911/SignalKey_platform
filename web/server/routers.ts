import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router, protectedProcedure } from "./_core/trpc";
import { z } from "zod";
import { User, AppConfig, TradingSignal, Trade, VirtualBalance, connectMongo } from "./mongodb";

// Asegurar conexión a MongoDB
connectMongo();

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(async (opts) => {
      if (!opts.ctx.user) return null;
      // Sincronizar con MongoDB si es necesario
      let mongoUser = await User.findOne({ openId: opts.ctx.user.openId });
      if (!mongoUser) {
        mongoUser = await User.create({
          openId: opts.ctx.user.openId,
          name: opts.ctx.user.name,
          email: opts.ctx.user.email,
          role: opts.ctx.user.role
        });
      }
      return mongoUser;
    }),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),

  trading: router({
    getConfig: protectedProcedure.query(async ({ ctx }) => {
      const mongoUser = await User.findOne({ openId: ctx.user.openId });
      if (!mongoUser) return null;
      return await AppConfig.findOne({ userId: mongoUser._id });
    }),
    updateConfig: protectedProcedure
      .input(z.object({
        demoMode: z.boolean().optional(),
        geminiApiKey: z.string().optional(),
        gmgnApiKey: z.string().optional(),
        telegramBotToken: z.string().optional(),
        telegramChatId: z.string().optional(),
        telegramChannels: z.object({
          allow: z.array(z.string()).optional(),
          deny: z.array(z.string()).optional()
        }).optional(),
        exchanges: z.array(z.object({
          exchangeId: z.string(),
          apiKey: z.string(),
          secret: z.string(),
          password: z.string().optional(),
          uid: z.string().optional(),
          isActive: z.boolean().optional()
        })).optional(),
        dexConfig: z.object({
          walletPrivateKey: z.string().optional(),
          rpcUrl: z.string().optional()
        }).optional(),
        investmentLimits: z.object({
          cexMaxAmount: z.number().optional(),
          dexMaxAmount: z.number().optional()
        }).optional()
      }))
      .mutation(async ({ ctx, input }) => {
        const mongoUser = await User.findOne({ openId: ctx.user.openId });
        if (!mongoUser) throw new Error("User not found in MongoDB");

        await AppConfig.findOneAndUpdate(
          { userId: mongoUser._id },
          { $set: input },
          { upsert: true, new: true }
        );
        return { success: true };
      }),
    getSignals: protectedProcedure.query(async ({ ctx }) => {
      const mongoUser = await User.findOne({ openId: ctx.user.openId });
      if (!mongoUser) return [];
      return await TradingSignal.find({ userId: mongoUser._id }).sort({ createdAt: -1 }).limit(50);
    }),
    getTrades: protectedProcedure.query(async ({ ctx }) => {
      const mongoUser = await User.findOne({ openId: ctx.user.openId });
      if (!mongoUser) return [];
      return await Trade.find({ userId: mongoUser._id }).sort({ createdAt: -1 }).limit(100);
    }),
    getBalances: protectedProcedure.query(async ({ ctx }) => {
      const mongoUser = await User.findOne({ openId: ctx.user.openId });
      if (!mongoUser) return [];
      return await VirtualBalance.find({ userId: mongoUser._id });
    }),
  }),
});

export type AppRouter = typeof appRouter;
