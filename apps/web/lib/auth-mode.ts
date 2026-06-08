export function isAuthDevSkipped() {
  return process.env.AUTH_DEV_SKIP_SIGN_IN === "true";
}

