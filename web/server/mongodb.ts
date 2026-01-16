import mongoose, { Schema, Document } from 'mongoose';
import { ENV } from './_core/env';

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/signalkey_platform';

export const connectMongo = async () => {
  if (mongoose.connection.readyState >= 1) return;
  try {
    await mongoose.connect(MONGODB_URI);
    console.log('Connected to MongoDB');
  } catch (error) {
    console.error('MongoDB connection error:', error);
  }
};

// User Schema
const UserSchema = new Schema({
  openId: { type: String, required: true, unique: true },
  name: String,
  email: String,
  role: { type: String, enum: ['user', 'admin'], default: 'user' },
  lastSignedIn: { type: Date, default: Date.now },
}, { timestamps: true });

export const User = mongoose.models.User || mongoose.model('User', UserSchema);

// App Config Schema
const AppConfigSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  demoMode: { type: Boolean, default: true },
  geminiApiKey: String,
  gmgnApiKey: String,
  telegramBotToken: String,
  telegramChatId: String,
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
  }
}, { timestamps: true });

export const AppConfig = mongoose.models.AppConfig || mongoose.model('AppConfig', AppConfigSchema);

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

export const TradingSignal = mongoose.models.TradingSignal || mongoose.model('TradingSignal', TradingSignalSchema);

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

export const Trade = mongoose.models.Trade || mongoose.model('Trade', TradeSchema);

// Virtual Balance Schema
const VirtualBalanceSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, ref: 'User', required: true },
  marketType: String,
  asset: String,
  amount: Number
}, { timestamps: true });

export const VirtualBalance = mongoose.models.VirtualBalance || mongoose.model('VirtualBalance', VirtualBalanceSchema);
