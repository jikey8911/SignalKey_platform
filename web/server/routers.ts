import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router, protectedProcedure } from "./_core/trpc";
import { z } from "zod";
import { User, AppConfig, TradingSignal, Trade, VirtualBalance, connectMongo } from "./mongodb";

// Asegurar conexión a MongoDB
connectMongo();

const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || `http://localhost:${BACKEND_PORT}`;

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

      // Asegurar que exista AppConfig
      let config = await AppConfig.findOne({ userId: mongoUser._id });
      if (!config) {
        await AppConfig.create({
          userId: mongoUser._id,
          demoMode: true,
          investmentLimits: { cexMaxAmount: 100, dexMaxAmount: 1 },
          virtualBalances: { cex: 10000, dex: 10 }
        });

        // Inicializar VirtualBalances si no existen
        const hasBalances = await VirtualBalance.exists({ userId: mongoUser._id });
        if (!hasBalances) {
          await VirtualBalance.insertMany([
            { userId: mongoUser._id, marketType: 'CEX', asset: 'USDT', amount: 10000 },
            { userId: mongoUser._id, marketType: 'DEX', asset: 'SOL', amount: 10 }
          ]);
        }
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
    getTelegramLogs: protectedProcedure.query(async ({ ctx }) => {
      try {
        const logs = await fetch(`${INTERNAL_API_URL}/telegram/logs?limit=200`)
          .then(res => res.json())
          .catch(() => []);
        return logs || [];
      } catch (e) {
        console.error("Error fetching telegram logs:", e);
        return [];
      }
    }),
    getConfig: protectedProcedure.query(async ({ ctx }) => {
      const mongoUser = await User.findOne({ openId: ctx.user.openId });
      if (!mongoUser) return null;
      return await AppConfig.findOne({ userId: mongoUser._id });
    }),
    updateConfig: protectedProcedure
      .input(z.object({
        demoMode: z.boolean().optional(),
        isAutoEnabled: z.boolean().optional(),
        aiProvider: z.enum(['gemini', 'openai', 'perplexity', 'grok']).optional(),
        aiApiKey: z.string().optional(),
        geminiApiKey: z.string().optional(),
        openaiApiKey: z.string().optional(),
        perplexityApiKey: z.string().optional(),
        grokApiKey: z.string().optional(),
        gmgnApiKey: z.string().optional(),
        zeroExApiKey: z.string().optional(),
        // Telegram fields
        telegramApiId: z.string().optional(),
        telegramApiHash: z.string().optional(),
        telegramPhoneNumber: z.string().optional(),
        telegramSessionString: z.string().optional(),
        telegramIsConnected: z.boolean().optional(),
        telegramBotToken: z.string().optional(),
        telegramChatId: z.string().optional(),
        telegramChannels: z.object({
          allow: z.array(z.string()).optional(),
          deny: z.array(z.string()).optional()
        }).optional(),
        exchanges: z.array(z.object({
          exchangeId: z.string(),
          apiKey: z.string().optional(),
          secret: z.string().optional(),
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
        }).optional(),
        virtualBalances: z.object({
          cex: z.number().optional(),
          dex: z.number().optional()
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

      try {
        // Intentar obtener balances enriquecidos desde la API (incluye balance real del exchange)
        const res = await fetch(`${INTERNAL_API_URL}/balances/${ctx.user.openId}`);
        if (res.ok) {
          const data = await res.json();
          return data;
        }
      } catch (e) {
        console.error("Error fetching balances from API, falling back to DB:", e);
      }

      // Fallback a solo balances virtuales de la DB
      return await VirtualBalance.find({ userId: mongoUser._id });
    }),
  }),
});

export type AppRouter = typeof appRouter;
