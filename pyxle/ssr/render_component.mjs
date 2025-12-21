import { Console } from 'node:console';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const REACT_EXTERNALS = [
  'react',
  'react-dom',
  'react-dom/server',
  'react/jsx-runtime',
  'react/jsx-dev-runtime',
];

async function render() {
  const [, , componentPath, propsJson, clientRoot, projectRootArg] = process.argv;

  if (!componentPath) {
    throw new Error('Missing component path argument.');
  }

  redirectConsoleToStderr();

  const props = propsJson ? JSON.parse(propsJson) : {};
  const workingDir = clientRoot ? path.resolve(clientRoot) : path.dirname(componentPath);
  const projectRoot = resolveProjectRoot(projectRootArg, workingDir, componentPath);
  if (!projectRoot) {
    throw new Error('Unable to determine project root for SSR runtime.');
  }
  const styleRegistry = createStyleRegistry(projectRoot);
  globalThis.__PYXLE_REGISTER_SSR_STYLE__ = (entry) => styleRegistry.register(entry);
  const projectRequire = createProjectRequire(projectRoot);
  const esbuild = loadDependency('esbuild', projectRequire, projectRoot);
  const React = loadDependency('react', projectRequire, projectRoot);
  const ReactDOMServer = loadDependency('react-dom/server', projectRequire, projectRoot);
  const tempDir = createProjectTempDir(projectRoot);
  const outfile = path.join(tempDir, 'bundle.mjs');

  try {
    await esbuild.build({
      entryPoints: [componentPath],
      bundle: true,
      format: 'esm',
      platform: 'node',
      outfile,
      jsx: 'automatic',
      sourcemap: false,
      logLevel: 'silent',
      absWorkingDir: workingDir,
      plugins: [
        {
          name: 'pyxle-pages-alias',
          setup(build) {
            build.onResolve({ filter: /^\/(pages|routes)\// }, (args) => ({
              path: path.resolve(workingDir, args.path.slice(1)),
            }));

            build.onResolve({ filter: /^pyxle\/client(?:\/.*)?$/ }, (args) => {
              const remainder = args.path.slice('pyxle/client'.length);
              const normalized = remainder === '' || remainder === '/'
                ? 'pyxle/index.js'
                : `pyxle${remainder}`;
              return {
                path: path.resolve(workingDir, normalized),
              };
            });
          },
        },
        {
          name: 'pyxle-inline-css',
          setup(build) {
            build.onLoad({ filter: /\.css$/ }, async (args) => {
              const contents = await fs.promises.readFile(args.path, 'utf8');
              const descriptor = styleRegistry.describe(args.path, contents);
              const moduleCode = `const entry = ${JSON.stringify(descriptor)};
if (typeof globalThis.__PYXLE_REGISTER_SSR_STYLE__ === 'function') {
  globalThis.__PYXLE_REGISTER_SSR_STYLE__(entry);
}
export default entry.contents;
`;
              return {
                contents: moduleCode,
                loader: 'js',
                resolveDir: path.dirname(args.path),
              };
            });
          },
        },
      ],
      external: REACT_EXTERNALS,
    });

    const moduleUrl = pathToFileURL(outfile).href;
    const moduleExports = await import(moduleUrl);
    const Component = moduleExports.default ?? moduleExports.Component;

    if (typeof Component !== 'function') {
      throw new Error('Component does not export a default function.');
    }

    const element = React.createElement(Component, props);
    const html = ReactDOMServer.renderToString(element);
    const styles = styleRegistry.list();
    process.stdout.write(JSON.stringify({ ok: true, html, styles }));
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

render().catch((error) => {
  process.stderr.write(
    JSON.stringify({
      ok: false,
      message: error.message,
      stack: error.stack,
    })
  );
  process.exit(1);
});

function resolveProjectRoot(projectRootArg, workingDir, componentPath) {
  if (projectRootArg && projectRootArg !== 'undefined') {
    return path.resolve(projectRootArg);
  }

  const inferredFromClient = workingDir ? path.resolve(workingDir, '..', '..') : null;
  if (inferredFromClient && fs.existsSync(inferredFromClient)) {
    return inferredFromClient;
  }

  let current = path.dirname(componentPath);
  while (current && current !== path.dirname(current)) {
    if (path.basename(current) === 'client' && path.basename(path.dirname(current)) === '.pyxle-build') {
      return path.dirname(path.dirname(current));
    }
    current = path.dirname(current);
  }
  return null;
}

function createProjectRequire(projectRoot) {
  if (!projectRoot) {
    return null;
  }
  const virtualEntry = path.join(projectRoot, 'pyxle-ssr-runtime.js');
  return createRequire(virtualEntry);
}

function createProjectTempDir(projectRoot) {
  const baseDir = path.join(projectRoot, '.pyxle-build', '.ssr-tmp');
  fs.mkdirSync(baseDir, { recursive: true });
  return fs.mkdtempSync(path.join(baseDir, 'run-'));
}

function loadDependency(specifier, projectRequire, projectRoot) {
  const loaders = [];
  if (projectRequire) {
    loaders.push(projectRequire);
  }
  loaders.push(createRequire(import.meta.url));

  let lastError;
  for (const loader of loaders) {
    try {
      return loader(specifier);
    } catch (error) {
      lastError = error;
    }
  }

  const location = projectRoot ? ` from '${projectRoot}'` : '';
  throw new Error(
    `Unable to resolve '${specifier}'${location}. Install it in your project with 'npm install ${specifier}'.`,
    { cause: lastError }
  );
}

function redirectConsoleToStderr() {
  const redirected = new Console({ stdout: process.stderr, stderr: process.stderr });
  const methods = ['log', 'info', 'warn', 'error', 'debug', 'dir', 'trace'];

  for (const method of methods) {
    if (typeof redirected[method] === 'function') {
      console[method] = (...args) => redirected[method](...args);
    }
  }
}

function createStyleRegistry(projectRoot) {
  const map = new Map();

  return {
    register(entry) {
      if (!entry || typeof entry !== 'object') {
        return;
      }
      const { identifier } = entry;
      if (typeof identifier !== 'string' || map.has(identifier)) {
        return;
      }
      map.set(identifier, entry);
    },
    describe(filePath, contents) {
      const source = normalizeStyleSource(filePath, projectRoot);
      return {
        identifier: makeStyleIdentifier(source),
        source,
        contents,
      };
    },
    list() {
      return Array.from(map.values());
    },
  };
}

function normalizeStyleSource(filePath, projectRoot) {
  const absolute = path.resolve(filePath);
  if (projectRoot) {
    const relative = path.relative(projectRoot, absolute);
    if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
      return relative.split(path.sep).join('/');
    }
  }
  return path.basename(filePath);
}

function makeStyleIdentifier(source) {
  const base = typeof source === 'string' && source ? source : 'style';
  const digest = crypto.createHash('sha1').update(base).digest('hex').slice(0, 12);
  const safe = base.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'style';
  return `pyxle-inline-style-${safe}-${digest}`;
}
