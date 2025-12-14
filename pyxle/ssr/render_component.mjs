import { Console } from 'node:console';
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
      ],
      loader: {
        '.css': 'text',
      },
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
    process.stdout.write(JSON.stringify({ ok: true, html }));
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
