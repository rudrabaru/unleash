// Development tools are off in a normal build: raw scores, the technical reasons from the backend and the
// "save recording" button only appear when the site is started with NEXT_PUBLIC_DEBUG=1.
export const DEBUG = process.env.NEXT_PUBLIC_DEBUG === "1";
