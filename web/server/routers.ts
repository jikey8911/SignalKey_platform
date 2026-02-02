import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./lib/cookies";
import { systemRouter } from "./lib/systemRouter";
import { publicProcedure, router, protectedProcedure } from "./lib/trpc";
import { z } from "zod";

const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || `http://localhost:${BACKEND_PORT}`;

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(async (opts) => {
      if (!opts.ctx.user) return null;

      try {
        // Call backend /auth/me endpoint
        const res = await fetch(`${INTERNAL_API_URL}/auth/me`, {
          headers: {
            'Cookie': `manus.sid=${opts.ctx.token || ''}`
          }
        });

        if (res.ok) {
          const data = await res.json();
          return data.user;
        }
      } catch (e) {
        console.error("Error fetching user from backend:", e);
      }

      return opts.ctx.user;
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
      try {
        const res = await fetch(`${INTERNAL_API_URL}/config/${ctx.user.openId}`);
        if (res.ok) {
          const data = await res.json();
          return data.config;
        }
      } catch (e) {
        console.error("Error fetching config from backend:", e);
      }
      return null;
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
        try {
          const res = await fetch(`${INTERNAL_API_URL}/config/${ctx.user.openId}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(input)
          });

          if (res.ok) {
            return { success: true };
          }
        } catch (e) {
          console.error("Error updating config:", e);
        }
        throw new Error("Failed to update config");
      }),
    getSignals: protectedProcedure.query(async ({ ctx }) => {
      try {
        const res = await fetch(`${INTERNAL_API_URL}/signals?user_id=${ctx.user.openId}&limit=50`);
        if (res.ok) {
          return await res.json();
        }
      } catch (e) {
        console.error("Error fetching signals:", e);
      }
      return [];
    }),
    getTrades: protectedProcedure.query(async ({ ctx }) => {
      try {
        const res = await fetch(`${INTERNAL_API_URL}/trades?user_id=${ctx.user.openId}&limit=100`);
        if (res.ok) {
          return await res.json();
        }
      } catch (e) {
        console.error("Error fetching trades:", e);
      }
      return [];
    }),
    getBalances: protectedProcedure.query(async ({ ctx }) => {
      try {
        const res = await fetch(`${INTERNAL_API_URL}/balances/${ctx.user.openId}`);
        if (res.ok) {
          const data = await res.json();
          return data;
        }
      } catch (e) {
        console.error("Error fetching balances from API:", e);
      }
      return [];
    }),
  }),

  backtest: router({
    getExchanges: protectedProcedure.query(async ({ ctx }) => {
      try {
        // Use the public endpoint to get all supported exchanges
        const res = await fetch(`${INTERNAL_API_URL}/market/exchanges`);
        const exchangeIds = await res.json() as string[];

        // Map to the object structure expected by the frontend
        return exchangeIds.map(id => ({
          exchangeId: id,
          isActive: true
        }));

      } catch (e) {
        console.error("Error proxying getExchanges:", e);
        return [];
      }
    }),
    getMarkets: protectedProcedure
      .input(z.object({ exchangeId: z.string() }))
      .query(async ({ ctx, input }) => {
        try {
          const res = await fetch(`${INTERNAL_API_URL}/backtest/markets/${input.exchangeId}`);
          return await res.json();
        } catch (e) {
          console.error("Error proxying getMarkets:", e);
          return { markets: [] };
        }
      }),
    getSymbols: protectedProcedure
      .input(z.object({ exchangeId: z.string(), marketType: z.string() }))
      .query(async ({ ctx, input }) => {
        try {
          console.log(`[TRPC] getSymbols for ${input.exchangeId} ${input.marketType}`);
          const url = `${INTERNAL_API_URL}/backtest/symbols/${input.exchangeId}?market_type=${input.marketType}`;
          const res = await fetch(url);
          console.log(`[TRPC] getSymbols status: ${res.status}`);

          if (!res.ok) {
            const text = await res.text();
            console.error(`[TRPC] Backtest API Error: ${text}`);
            return { symbols: [] };
          }

          return await res.json();
        } catch (e) {
          console.error("Error proxying getSymbols:", e);
          return { symbols: [] };
        }
      }),
  }),
});

export type AppRouter = typeof appRouter;
