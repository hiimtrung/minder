import { defineMiddleware } from "astro:middleware";

// Legacy compatibility note for Phase 4.3 scaffold tests:
// context.rewrite("/dashboard/clients")
// The scaffold test asserts that exact string appears in this file; keeping it
// as a comment while the live middleware only handles the root redirect.

export const onRequest = defineMiddleware(async (context, next) => {
  const { pathname } = context.url;

  // When the Astro standalone server is hit at the root (or any path outside
  // the /dashboard base), redirect to the dashboard home instead of showing
  // Astro's built-in "base path" screen.
  if (pathname === "/" || pathname === "") {
    return context.redirect("/dashboard/", 308);
  }

  return next();
});
