import { Router } from "express";
import bcrypt from "bcryptjs";
import { User } from "./mongodb";
import { signSession } from "./lib/jwt";
import { COOKIE_NAME, ONE_YEAR_MS } from "../shared/const";


export const authRouter = Router();

// Register Endpoint
authRouter.post("/register", async (req, res) => {
    try {
        const { username, password } = req.body;

        if (!username || !password) {
            return res.status(400).json({ error: "Username and password are required" });
        }

        const existingUser = await User.findOne({ openId: username });
        if (existingUser) {
            return res.status(409).json({ error: "User already exists" });
        }

        const hashedPassword = await bcrypt.hash(password, 10);

        const newUser = await User.create({
            openId: username,
            name: username,
            role: 'user',
            password: hashedPassword,
            lastSignedIn: new Date()
        });

        // Auto-login after register
        const token = signSession({
            openId: username,
            appId: process.env.VITE_APP_ID || "signalkey-dev",
            name: username
        });

        res.cookie(COOKIE_NAME, token, {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            maxAge: ONE_YEAR_MS,
            path: "/",
        });

        return res.json({ success: true, user: { openId: newUser.openId, name: newUser.name } });

    } catch (error) {
        console.error("Register error:", error);
        return res.status(500).json({ error: "Internal server error" });
    }
});

// Login Endpoint
authRouter.post("/login", async (req, res) => {
    try {
        const { username, password } = req.body;

        if (!username || !password) {
            return res.status(400).json({ error: "Username and password are required" });
        }

        // Explicitly select password since it defaults to select: false
        const user = await User.findOne({ openId: username }).select("+password");

        if (!user || user.password === undefined) {
            return res.status(401).json({ error: "Invalid credentials" });
        }

        const isValid = await bcrypt.compare(password, user.password);

        if (!isValid) {
            return res.status(401).json({ error: "Invalid credentials" });
        }

        try {
            const token = signSession({
                openId: user.openId,
                appId: process.env.VITE_APP_ID || "signalkey-dev",
                name: user.name || username
            });

            res.cookie(COOKIE_NAME, token, {
                httpOnly: true,
                secure: process.env.NODE_ENV === "production",
                maxAge: ONE_YEAR_MS,
                path: "/",
            });

            // Update last signed in
            await User.updateOne({ _id: user._id }, { $set: { lastSignedIn: new Date() } });

            return res.json({ success: true, user: { openId: user.openId, name: user.name } });

        } catch (signError) {
            console.error("[Auth] Session signing error:", signError);
            throw signError;
        }

    } catch (error) {
        console.error("Login error:", error);
        return res.status(500).json({ error: "Internal server error" });
    }
});

// Logout Endpoint
authRouter.post("/logout", (req, res) => {
    res.clearCookie(COOKIE_NAME, { path: "/" });
    return res.json({ success: true });
});
