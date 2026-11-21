import "server-only";
import { Resolver } from "node:dns/promises";
import mongoose from "mongoose";

/**
 * One shared connection. The promise is kept on the mongoose module itself (one copy per process, since Next loads
 * mongoose as an external package), not on globalThis: instrumentation.ts and the pages can run in different
 * module contexts, and two separate connect() calls made the second one fail ("different connection strings").
 */
const cache = mongoose as typeof mongoose & { _structuraConn?: Promise<typeof mongoose> };

/**
 * A `mongodb+srv://` URI makes the driver look up a DNS SRV record (the hosts) AND a TXT record (extra options).
 * Some networks never answer TXT queries, so the driver hangs for ~90 s before failing and every page that reads
 * the database waits with it. We do the lookups ourselves with short timeouts and connect with a plain
 * `mongodb://host1,host2,host3/...` URI. The driver discovers the replica set from those hosts on its own.
 */
async function resolveUri(uri: string): Promise<string> {
  if (!uri.startsWith("mongodb+srv://")) return uri;
  const url = new URL(uri.replace(/^mongodb\+srv:/, "https:"));
  const resolver = new Resolver({ timeout: 3000, tries: 1 });
  const srv = await resolver.resolveSrv(`_mongodb._tcp.${url.hostname}`);
  const params = new URLSearchParams(url.search);
  try {
    // options published by the cluster (authSource, replicaSet), when this network lets us read them
    for (const [k, v] of new URLSearchParams((await resolver.resolveTxt(url.hostname)).flat().join("&"))) {
      if (!params.has(k)) params.set(k, v);
    }
  } catch {
    // TXT blocked: Atlas only puts authSource=admin and the replica set name there; the set is discovered anyway
  }
  if (!params.has("authSource")) params.set("authSource", "admin");
  if (!params.has("tls") && !params.has("ssl")) params.set("tls", "true");
  const auth = url.username ? `${url.username}:${url.password}@` : "";
  return `mongodb://${auth}${srv.map((s) => `${s.name}:${s.port}`).sort().join(",")}${url.pathname}?${params}`;
}

export function connectDB(): Promise<typeof mongoose> {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    throw new Error("MONGODB_URI is not set. Add it to frontend/.env.local.");
  }
  const state = mongoose.connection.readyState; // 0 closed, 1 open, 2 connecting, 3 closing
  if (state === 1) return Promise.resolve(mongoose);
  if (!cache._structuraConn && state === 2) cache._structuraConn = mongoose.connection.asPromise().then(() => mongoose);
  if (!cache._structuraConn) {
    cache._structuraConn = resolveUri(uri)
      .catch(() => uri) // SRV lookup failed too: let the driver try the original URI
      .then((resolved) => mongoose.connect(resolved, {
        serverSelectionTimeoutMS: 8000,
        // A new TLS connection to Atlas costs ~3-4 s from here, so requests must never wait for one: keep a few
        // sockets open for good. Do NOT set maxIdleTimeMS: retiring idle sockets made requests wait for new ones
        // (2-6 s loads). After a network drop, the 5 s heartbeat notices and the pool reconnects; a query stuck on
        // a dead socket fails within 10 s and lib/data.ts retries reads once.
        minPoolSize: 4,
        socketTimeoutMS: 10_000,
        heartbeatFrequencyMS: 5_000,
        family: 4, // skip slow IPv6 attempts on networks without IPv6
      }))
      .then((m) => {
        // surface connection trouble in the server log (messages only, never the URI)
        for (const ev of ["disconnected", "reconnected", "error"] as const) {
          m.connection.on(ev, (e?: Error) => console.warn(`[db] ${ev}${e?.message ? `: ${e.message}` : ""}`));
        }
        return m;
      })
      .catch((err: unknown) => {
        console.error("[db] connect failed:", err instanceof Error ? `${err.name}: ${err.message}` : err);
        cache._structuraConn = undefined; // allow a retry on the next request
        throw err;
      });
  }
  return cache._structuraConn;
}
