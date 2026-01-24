import mongoose, { Schema, Document } from 'mongoose';
import { ENV } from './_core/env';

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/signalkey_platform';

export const connectMongo = async () => {
  if (mongoose.connection.readyState >= 1) {
    console.log('[MongoDB] Connection already active');
    return;
  }
  try {
    console.log('[MongoDB] Attempting to connect to:', MONGODB_URI);
    await mongoose.connect(MONGODB_URI, { serverSelectionTimeoutMS: 5000 });
    console.log('[MongoDB] Connected successfully');

    // Add event listeners for connection events
    mongoose.connection.on('connected', () => {
      console.log('[MongoDB] Mongoose default connection open to ' + MONGODB_URI);
    });

    mongoose.connection.on('error', (err) => {
      console.error('[MongoDB] Mongoose default connection error: ' + err);
    });

    mongoose.connection.on('disconnected', () => {
      console.log('[MongoDB] Mongoose default connection disconnected');
    });

  } catch (error) {
    console.error('[MongoDB] Connection error:', error);
  }
};

// User Schema
const UserSchema = new Schema({
  openId: { type: String, required: true, unique: true },
  name: String,
  email: String,
  role: { type: String, enum: ['user', 'admin'], default: 'user' },
  password: { type: String, select: false }, // Added for local auth
  lastSignedIn: { type: Date, default: Date.now },
}, { timestamps: true });

export const User = mongoose.models.User || mongoose.model('User', UserSchema, 'users');

// App Config Schema
const AppConfigSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  demoMode: { type: Boolean, default: true },
  isAutoEnabled: { type: Boolean, default: true },
  aiProvider: { type: String, enum: ['gemini', 'openai', 'perplexity', 'grok'], default: 'gemini' },
  aiApiKey: String, // Fallback/Legacy
  geminiApiKey: String,
  openaiApiKey: String,
  perplexityApiKey: String,
  grokApiKey: String,
  gmgnApiKey: String,
  zeroExApiKey: String,
  // Telegram Configuration (per user)
  telegramApiId: String,
  telegramApiHash: String,
  telegramPhoneNumber: String,
  telegramSessionString: String, // Serialized session
  telegramIsConnected: { type: Boolean, default: false },
  telegramLastConnected: Date,
  telegramBotToken: String, // Legacy field
  telegramChatId: String,
  telegramChannels: {
    allow: [String],
    deny: [String]
  },
  exchanges: [{
    exchangeId: { type: String, default: 'binance' },
    apiKey: String,
    secret: String,
    password: String,
    uid: String,
    isActive: { type: Boolean, default: true }
  }],
  dexConfig: {
    walletPrivateKey: String,
    rpcUrl: { type: String, default: 'https://api.mainnet-beta.solana.com' }
  },
  investmentLimits: {
    cexMaxAmount: { type: Number, default: 100 },
    dexMaxAmount: { type: Number, default: 1 }
  },
  virtualBalances: {
    cex: { type: Number, default: 10000 },
    dex: { type: Number, default: 10 }
  }
}, { timestamps: true });

export const AppConfig = mongoose.models.AppConfig || mongoose.model('AppConfig', AppConfigSchema, 'app_configs');

// Trading Signal Schema
const TradingSignalSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  source: String,
  rawText: String,
  decision: String,
  symbol: String,
  marketType: String,
  confidence: Number,
  reasoning: String,
  status: { type: String, default: 'pending' }
}, { timestamps: true });

export const TradingSignal = mongoose.models.TradingSignal || mongoose.model('TradingSignal', TradingSignalSchema, 'trading_signals');

// Trade Schema
const TradeSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  signalId: { type: Schema.Types.ObjectId, ref: 'TradingSignal' },
  symbol: String,
  side: String,
  price: Number,
  amount: Number,
  marketType: String,
  isDemo: { type: Boolean, default: true },
  orderId: String,
  status: { type: String, default: 'pending' },
  pnl: Number,
  executedAt: Date
}, { timestamps: true });

export const Trade = mongoose.models.Trade || mongoose.model('Trade', TradeSchema, 'trades');

// Virtual Balance Schema
const VirtualBalanceSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  marketType: String,
  asset: String,
  amount: Number
}, { timestamps: true });

export const VirtualBalance = mongoose.models.VirtualBalance || mongoose.model('VirtualBalance', VirtualBalanceSchema, 'virtual_balances');
