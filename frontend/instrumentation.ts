/**
 * Runs once when the server starts. Opens the MongoDB connection right away, so the first visitor
 * does not wait ~4 s for the TLS handshake to Atlas.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs" || !process.env.MONGODB_URI) return;
  const { connectDB } = await import("./lib/db");
  connectDB().catch(() => {
    // not fatal: the first request retries the connection
  });
}
