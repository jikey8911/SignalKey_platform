CREATE TABLE `app_config` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`demoMode` int NOT NULL DEFAULT 1,
	`geminiApiKey` text,
	`gmgnApiKey` text,
	`telegramBotToken` text,
	`exchangeId` varchar(64) DEFAULT 'binance',
	`cexApiKey` text,
	`cexSecret` text,
	`cexPassword` text,
	`cexUid` text,
	`dexWalletPrivateKey` text,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `app_config_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `trades` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`signalId` int,
	`symbol` varchar(128) NOT NULL,
	`side` varchar(10) NOT NULL,
	`price` float NOT NULL,
	`amount` float NOT NULL,
	`marketType` varchar(20) NOT NULL,
	`isDemo` int NOT NULL DEFAULT 1,
	`orderId` varchar(256),
	`status` varchar(20) DEFAULT 'pending',
	`pnl` float,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`executedAt` timestamp,
	CONSTRAINT `trades_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `trading_signals` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`source` varchar(64) NOT NULL,
	`rawText` text NOT NULL,
	`decision` varchar(20) NOT NULL,
	`symbol` varchar(128) NOT NULL,
	`marketType` varchar(20) NOT NULL,
	`confidence` float DEFAULT 0,
	`reasoning` text,
	`status` varchar(20) DEFAULT 'pending',
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `trading_signals_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `virtual_balances` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`marketType` varchar(20) NOT NULL,
	`asset` varchar(64) NOT NULL,
	`amount` float NOT NULL,
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `virtual_balances_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
ALTER TABLE `app_config` ADD CONSTRAINT `app_config_userId_users_id_fk` FOREIGN KEY (`userId`) REFERENCES `users`(`id`) ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE `trades` ADD CONSTRAINT `trades_userId_users_id_fk` FOREIGN KEY (`userId`) REFERENCES `users`(`id`) ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE `trades` ADD CONSTRAINT `trades_signalId_trading_signals_id_fk` FOREIGN KEY (`signalId`) REFERENCES `trading_signals`(`id`) ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE `trading_signals` ADD CONSTRAINT `trading_signals_userId_users_id_fk` FOREIGN KEY (`userId`) REFERENCES `users`(`id`) ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE `virtual_balances` ADD CONSTRAINT `virtual_balances_userId_users_id_fk` FOREIGN KEY (`userId`) REFERENCES `users`(`id`) ON DELETE no action ON UPDATE no action;