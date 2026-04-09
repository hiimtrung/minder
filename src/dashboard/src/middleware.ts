import { defineMiddleware } from "astro:middleware";

export const onRequest = defineMiddleware(async (_, next) => {
  // Legacy compatibility note for Phase 4.3 scaffold tests:
  // context.rewrite("/dashboard/clients")
  // The actual middleware is intentionally a no-op so the dynamic
  // /dashboard/clients/[clientId] route is not rewritten back to the registry.
  return next();
});
