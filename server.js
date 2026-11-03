import express from "express";
import cron from "node-cron";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { refresh, loadPreds } from "./data.js";

const ADMIN = process.env.ADMIN_KEY;
if (!ADMIN) { console.error("Set ADMIN_KEY (see .env.example)"); process.exit(1); }
const FREE = +process.env.FREE_PER_DAY || 3, MAXDEV = +process.env.MAX_DEVICES || 2, LOCK = process.env.LOCK !== "off";
const CF = "data/codes.json"; fs.mkdirSync("data", { recursive: true });
const codes = (() => { try { return JSON.parse(fs.readFileSync(CF, "utf8")); } catch { return {}; } })();
const save = () => fs.writeFileSync(CF, JSON.stringify(codes));

const app = express();
app.set("trust proxy", 1);
app.use(express.json({ limit: "5kb" }));
// Serve only the app files (never data/ or the source). Works if they sit in ./public or beside server.js.
const root = path.resolve(fs.existsSync("public") ? "public" : ".");
for (const f of ["index.html", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"]) app.get("/" + f, (req, res) => res.sendFile(f, { root }));
app.get("/", (req, res) => res.sendFile("index.html", { root }));

const tries = new Map();
const guard = (req, res, next) => {
  const k = req.ip, t = (tries.get(k) || []).filter(x => x > Date.now() - 9e5);
  if (t.length >= 20) return res.status(429).json({ error: "Too many tries. Wait a few minutes." });
  t.push(Date.now()); tries.set(k, t); next();
};
const isPro = req => {
  if (!LOCK) return true;
  const c = codes[String(req.headers["x-access-code"] || "").toUpperCase()], dev = String(req.headers["x-device"] || "");
  return !!c && c.expires > Date.now() && c.devices.includes(dev);
};

app.post("/api/redeem", guard, (req, res) => {
  const code = String(req.body.code || "").trim().toUpperCase(), dev = String(req.body.device || ""), c = codes[code];
  if (!c || !dev) return res.status(400).json({ error: "That code is not valid." });
  if (!c.expires) c.expires = Date.now() + c.days * 864e5;           // the clock starts at first use
  if (c.expires < Date.now()) return res.status(400).json({ error: "That code has expired." });
  if (!c.devices.includes(dev)) {
    if (c.devices.length >= MAXDEV) return res.status(400).json({ error: `That code is already used on ${MAXDEV} devices.` });
    c.devices.push(dev);
  }
  save(); res.json({ plan: "pro", expires: c.expires });
});

app.get("/api/matches", (req, res) => {
  const date = String(req.query.date || "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return res.status(400).json({ error: "Bad date." });
  const pro = isPro(req);
  const list = loadPreds().matches.filter(m => m.date === date).sort((a, b) => (a.kickoff + a.competition).localeCompare(b.kickoff + b.competition));
  res.json({ plan: pro ? "pro" : "free", matches: list.map((m, i) => pro || i < FREE ? { ...m, locked: false }
    : { id: m.id, country: m.country, competition: m.competition, kickoff: m.kickoff, home: m.home, away: m.away, locked: true }) }); // locked ones carry no prediction
});

const admin = (req, res, next) => (req.headers["x-admin-key"] === ADMIN ? next() : res.status(403).json({ error: "Not allowed." }));
app.post("/api/admin/codes", admin, (req, res) => {
  const days = +req.body.days || 30, n = Math.min(+req.body.count || 1, 100), out = [];
  for (let i = 0; i < n; i++) { const c = "PRO-" + crypto.randomBytes(5).toString("hex").toUpperCase(); codes[c] = { days, expires: 0, devices: [] }; out.push(c); }
  save(); res.json({ codes: out, days });
});
app.post("/api/admin/refresh", admin, (req, res) => { refresh(true).catch(e => console.error(e.message)); res.json({ started: true }); });

cron.schedule("0 */12 * * *", () => refresh().catch(e => console.error("refresh failed:", e.message)));
if (Date.now() - loadPreds().updated > 6 * 36e5) refresh().catch(e => console.error("refresh failed:", e.message));
app.listen(process.env.PORT || 3000, () => console.log("Matchday running"));
