/** @type {import('next').NextConfig} */
export default {
  // `next build` on this machine intermittently died with a Windows access violation
  // (exit 3221225477 / 0xC0000005) inside the forked static-generation worker — roughly
  // 1 build in 6, independent of whether .next existed. Static generation for two trivial
  // routes does not need a worker pool, so it runs in-process instead.
  experimental: { workerThreads: false, cpus: 1 },
};
