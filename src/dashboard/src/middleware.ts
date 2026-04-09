import { defineMiddleware } from "astro:middleware";

export const onRequest = defineMiddleware(async (context, next) => {
  const { pathname } = context.url;

  if (/^\/dashboard\/clients\/[^/]+\/?$/.test(pathname)) {
    return context.rewrite("/dashboard/clients");
  }

  return next();
});
