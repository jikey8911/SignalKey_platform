import { float, int, mysqlEnum, mysqlTable, text, timestamp, varchar, json } from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  /**
   * Surrogate primary key. Auto-incremented numeric value managed by the database.
   * Use this for relations between tables.
   */
  id: int("id").autoincrement().primaryKey(),
  /** Manus OAuth identifier (openId) returned from the OAuth callback. Unique per user. */
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

export const appConfig = mysqlTable("app_configs", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull().references(() => users.id),

  // App Settings
  demoMode: int("demoMode").default(1).notNull(),
  isAutoEnabled: int("isAutoEnabled").default(1).notNull(),
  aiProvider: varchar("aiProvider", { length: 20 }).default("gemini"),

  // API Keys & Configs
  geminiApiKey: text("geminiApiKey"),
  aiApiKey: text("aiApiKey"), // Often same as geminiApiKey but kept for flexibility
  grokApiKey: text("grokApiKey"),
  openaiApiKey: text("openaiApiKey"),
  perplexityApiKey: text("perplexityApiKey"),

  gmgnApiKey: text("gmgnApiKey"),
  zeroExApiKey: text("zeroExApiKey"),

  // Telegram Config
  telegramBotToken: text("telegramBotToken"),
  telegramChatId: text("telegramChatId"),
  telegramApiHash: text("telegramApiHash"),
  telegramApiId: text("telegramApiId"),
  telegramPhoneNumber: text("telegramPhoneNumber"),
  telegramSessionString: text("telegramSessionString"),
  telegramIsConnected: int("telegramIsConnected").default(0),
  telegramLastConnected: timestamp("telegramLastConnected"),

  // JSON Complex Objects
  telegramChannels: json("telegramChannels"),
  dexConfig: json("dexConfig"),
  investmentLimits: json("investmentLimits"),
  virtualBalances: json("virtualBalances"),
  exchanges: json("exchanges"),

  // Deprecated / Compatibility Fields (Kept for now)
  exchangeId: varchar("exchangeId", { length: 64 }).default("binance"),
  cexApiKey: text("cexApiKey"),
  cexSecret: text("cexSecret"),
  cexPassword: text("cexPassword"),
  cexUid: text("cexUid"),
  dexWalletPrivateKey: text("dexWalletPrivateKey"),

  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export type AppConfig = typeof appConfig.$inferSelect;
export type InsertAppConfig = typeof appConfig.$inferInsert;

export const tradingSignals = mysqlTable("trading_signals", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull().references(() => users.id),
  source: varchar("source", { length: 64 }).notNull(),
  rawText: text("rawText").notNull(),
  decision: varchar("decision", { length: 20 }).notNull(),
  symbol: varchar("symbol", { length: 128 }).notNull(),
  marketType: varchar("marketType", { length: 20 }).notNull(),
  confidence: float("confidence").default(0.0),
  reasoning: text("reasoning"),
  status: varchar("status", { length: 20 }).default("pending"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type TradingSignal = typeof tradingSignals.$inferSelect;
export type InsertTradingSignal = typeof tradingSignals.$inferInsert;

export const trades = mysqlTable("trades", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull().references(() => users.id),
  signalId: int("signalId").references(() => tradingSignals.id),
  symbol: varchar("symbol", { length: 128 }).notNull(),
  side: varchar("side", { length: 10 }).notNull(),
  price: float("price").notNull(),
  amount: float("amount").notNull(),
  marketType: varchar("marketType", { length: 20 }).notNull(),
  isDemo: int("isDemo").default(1).notNull(),
  orderId: varchar("orderId", { length: 256 }),
  status: varchar("status", { length: 20 }).default("pending"),
  pnl: float("pnl"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  executedAt: timestamp("executedAt"),
});

export type Trade = typeof trades.$inferSelect;
export type InsertTrade = typeof trades.$inferInsert;

export const virtualBalances = mysqlTable("virtual_balances", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull().references(() => users.id),
  marketType: varchar("marketType", { length: 20 }).notNull(),
  asset: varchar("asset", { length: 64 }).notNull(),
  amount: float("amount").notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export type VirtualBalance = typeof virtualBalances.$inferSelect;
export type InsertVirtualBalance = typeof virtualBalances.$inferInsert;