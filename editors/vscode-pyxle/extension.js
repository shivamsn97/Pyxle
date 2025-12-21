const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');

const SEGMENTS_REQUEST = 'pyxle/segments';
const LANGUAGE_SELECTOR = { language: 'pyxle', scheme: 'file' };

/** @type {LanguageClient | null} */
let client = null;
/** @type {SegmentManager | null} */
let segments = null;

function activate(context) {
    const config = vscode.workspace.getConfiguration('pyxleLangserver');
    const command = config.get('command') || 'pyxle-langserver';
    const args = config.get('args') || ['--stdio'];

    const serverOptions = {
        run: { command, args },
        debug: { command, args }
    };

    const clientOptions = {
        documentSelector: [{ language: 'pyxle', scheme: 'file' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.pyx')
        }
    };

    client = new LanguageClient('pyxleLanguageServer', 'Pyxle Language Server', serverOptions, clientOptions);
    context.subscriptions.push(client.start());

    const startSegments = () => {
        if (!client) {
            return;
        }
        segments = new SegmentManager(client);
        context.subscriptions.push(segments);
        registerCompletionProvider(context, segments);
        registerHoverProvider(context, segments);
        registerDefinitionProvider(context, segments);
        registerDiagnosticBridge(context, segments);
    };

    if (typeof client.onReady === 'function') {
        client.onReady().then(startSegments, console.error);
    } else {
        startSegments();
    }
}

function registerCompletionProvider(context, manager) {
    const provider = vscode.languages.registerCompletionItemProvider(
        LANGUAGE_SELECTOR,
        {
            async provideCompletionItems(document, position, token, requestContext) {
                if (!manager) {
                    return undefined;
                }
                await manager.ensureLatest(document);
                const mapping = manager.mapPosition(document.uri, position);
                if (!mapping) {
                    return undefined;
                }
                await manager.ensureVirtualFile(document.uri); // guarantees latest snapshots
                const context = requestContext
                    ? {
                          triggerKind: requestContext.triggerKind,
                          triggerCharacter: requestContext.triggerCharacter,
                      }
                    : undefined;
                const result = await vscode.commands.executeCommand(
                    'vscode.executeCompletionItemProvider',
                    mapping.uri,
                    mapping.position,
                    requestContext?.triggerCharacter,
                    context
                );
                return translateCompletionResult(manager, mapping.uri, result);
            }
        },
        '.',
        '"',
        "'",
        '/',
        '<',
        '{',
        '(',
        ','
    );
    context.subscriptions.push(provider);
}

function registerHoverProvider(context, manager) {
    const provider = vscode.languages.registerHoverProvider(LANGUAGE_SELECTOR, {
        async provideHover(document, position) {
            if (!manager) {
                return undefined;
            }
            await manager.ensureLatest(document);
            const mapping = manager.mapPosition(document.uri, position);
            if (!mapping) {
                return undefined;
            }
            const hovers = await vscode.commands.executeCommand(
                'vscode.executeHoverProvider',
                mapping.uri,
                mapping.position
            );
            if (!Array.isArray(hovers) || hovers.length === 0) {
                return undefined;
            }
            const contents = [];
            let resolvedRange;
            for (const hover of hovers) {
                if (!hover) {
                    continue;
                }
                if (Array.isArray(hover.contents)) {
                    contents.push(...hover.contents);
                } else if (hover.contents) {
                    contents.push(hover.contents);
                }
                if (!resolvedRange && hover.range) {
                    const mapped = manager.mapRangeFromVirtual(mapping.uri, hover.range);
                    if (mapped) {
                        resolvedRange = mapped.range;
                    }
                }
            }
            if (!contents.length) {
                return undefined;
            }
            return new vscode.Hover(contents, resolvedRange);
        }
    });
    context.subscriptions.push(provider);
}

function registerDefinitionProvider(context, manager) {
    const provider = vscode.languages.registerDefinitionProvider(LANGUAGE_SELECTOR, {
        async provideDefinition(document, position) {
            if (!manager) {
                return undefined;
            }
            await manager.ensureLatest(document);
            const mapping = manager.mapPosition(document.uri, position);
            if (!mapping) {
                return undefined;
            }
            const result = await vscode.commands.executeCommand(
                'vscode.executeDefinitionProvider',
                mapping.uri,
                mapping.position
            );
            return translateDefinitionResult(manager, mapping.uri, result);
        }
    });
    context.subscriptions.push(provider);
}

function translateDefinitionResult(manager, originVirtualUri, result) {
    if (!result) {
        return undefined;
    }
    if (Array.isArray(result)) {
        const converted = [];
        for (const entry of result) {
            const mapped = translateDefinitionEntry(manager, originVirtualUri, entry);
            if (mapped) {
                if (Array.isArray(mapped)) {
                    converted.push(...mapped);
                } else {
                    converted.push(mapped);
                }
            }
        }
        return converted;
    }
    return translateDefinitionEntry(manager, originVirtualUri, result);
}

function translateCompletionResult(manager, virtualUri, result) {
    if (!result) {
        return result;
    }
    const translateItem = (item) => translateCompletionItem(manager, virtualUri, item);
    if (Array.isArray(result)) {
        return result.map(translateItem);
    }
    if (typeof result === 'object' && Array.isArray(result.items)) {
        result.items = result.items.map(translateItem);
        return result;
    }
    return result;
}

function translateCompletionItem(manager, virtualUri, item) {
    if (!item) {
        return item;
    }
    if (item.range) {
        const mapped = manager.mapRangeFromVirtual(virtualUri, item.range);
        if (mapped) {
            item.range = mapped.range;
        }
    }
    if (item.textEdit) {
        item.textEdit = translateTextEdit(manager, virtualUri, item.textEdit);
    }
    if (Array.isArray(item.additionalTextEdits)) {
        item.additionalTextEdits = item.additionalTextEdits
            .map((edit) => translateTextEdit(manager, virtualUri, edit))
            .filter(Boolean);
    }
    return item;
}

function translateTextEdit(manager, virtualUri, edit) {
    if (!edit) {
        return edit;
    }
    if (edit.insert && edit.replace) {
        const insert = manager.mapRangeFromVirtual(virtualUri, edit.insert);
        const replace = manager.mapRangeFromVirtual(virtualUri, edit.replace);
        if (insert && replace) {
            return new vscode.InsertReplaceEdit(edit.newText, insert.range, replace.range);
        }
        return edit;
    }
    const mapped = manager.mapRangeFromVirtual(virtualUri, edit.range);
    if (!mapped) {
        return edit;
    }
    return new vscode.TextEdit(mapped.range, edit.newText);
}

function translateDefinitionEntry(manager, originVirtualUri, entry) {
    if (!entry) {
        return undefined;
    }
    if (isLocationLink(entry)) {
        const targetRange = manager.mapRangeFromVirtual(entry.targetUri, entry.targetRange);
        const targetSelectionRange = manager.mapRangeFromVirtual(entry.targetUri, entry.targetSelectionRange);
        const originRange = entry.originSelectionRange ? manager.mapRangeFromVirtual(originVirtualUri, entry.originSelectionRange) : null;
        return {
            targetUri: targetRange?.uri ?? entry.targetUri,
            targetRange: targetRange?.range ?? entry.targetRange,
            targetSelectionRange: targetSelectionRange?.range ?? entry.targetSelectionRange,
            originSelectionRange: originRange?.range ?? entry.originSelectionRange,
        };
    }
    const mapped = manager.mapRangeFromVirtual(entry.uri, entry.range);
    if (!mapped) {
        return entry;
    }
    return new vscode.Location(mapped.uri, mapped.range);
}

function isLocationLink(value) {
    return Boolean(value && value.targetUri && value.targetRange);
}

function registerDiagnosticBridge(context, manager) {
    const collection = vscode.languages.createDiagnosticCollection('pyxle-bridge');
    context.subscriptions.push(collection);

    const syncDiagnostics = (uri) => {
        if (!manager || !manager.isVirtualUri(uri)) {
            return;
        }
        const diagnostics = vscode.languages.getDiagnostics(uri);
        const translated = manager.translateDiagnostics(uri, diagnostics);
        if (!translated) {
            return;
        }
        collection.set(translated.original, translated.diagnostics);
    };

    context.subscriptions.push(
        vscode.languages.onDidChangeDiagnostics((event) => {
            for (const uri of event.uris) {
                syncDiagnostics(uri);
            }
        })
    );

    vscode.languages.getDiagnostics().forEach(([uri]) => syncDiagnostics(uri));

    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument((doc) => {
            collection.delete(doc.uri);
        })
    );
}

function deactivate() {
    if (segments) {
        segments.dispose();
        segments = null;
    }
    if (!client) {
        return undefined;
    }
    const stop = client.stop();
    client = null;
    return stop;
}

class SegmentManager {
    /** @param {LanguageClient} client */
    constructor(client) {
        this.client = client;
        this.cache = new Map();
        this.pending = new Map();
        this.virtualPaths = new Map();
        this.virtualIndex = new Map();
        this.disposables = [];

        this.disposables.push(
            vscode.workspace.onDidOpenTextDocument((doc) => this._handleDocument(doc)),
            vscode.workspace.onDidChangeTextDocument((event) => this._handleDocument(event.document)),
            vscode.workspace.onDidCloseTextDocument((doc) => {
                const key = doc.uri.toString();
                this.cache.delete(key);
                this._removeVirtualPaths(key);
            })
        );

        vscode.workspace.textDocuments.forEach((doc) => this._handleDocument(doc));
    }

    dispose() {
        this.disposables.forEach((d) => d.dispose());
        this.disposables = [];
        for (const handle of this.pending.values()) {
            clearTimeout(handle);
        }
        this.pending.clear();
    }

    _handleDocument(document) {
        if (document.languageId !== 'pyxle') {
            return;
        }
        this._scheduleRefresh(document);
    }

    _scheduleRefresh(document) {
        const key = document.uri.toString();
        if (this.pending.has(key)) {
            clearTimeout(this.pending.get(key));
        }
        const handle = setTimeout(() => {
            this.pending.delete(key);
            void this._refresh(document);
        }, 150);
        this.pending.set(key, handle);
    }

    async ensureLatest(document) {
        await this._refresh(document);
    }

    async _refresh(document) {
        try {
            const response = await this.client.sendRequest(SEGMENTS_REQUEST, { uri: document.uri.toString() });
            if (!response) {
                return;
            }
            const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
            if (!workspaceFolder) {
                return;
            }
            const virtualRoot = path.join(workspaceFolder.uri.fsPath, '.pyxle', '.lang-virtual');
            await this._writeVirtualFile(virtualRoot, workspaceFolder.uri.fsPath, document.uri, 'python', response.python?.code || '');
            await this._writeVirtualFile(virtualRoot, workspaceFolder.uri.fsPath, document.uri, 'jsx', response.jsx?.code || '');
            this.cache.set(document.uri.toString(), {
                python: {
                    lineNumbers: response.python?.lineNumbers || [],
                },
                jsx: {
                    lineNumbers: response.jsx?.lineNumbers || [],
                }
            });
        } catch (error) {
            console.error('Failed to refresh Pyxle segments', error);
        }
    }

    async _writeVirtualFile(root, workspaceRoot, originalUri, kind, content) {
        const relative = path.relative(workspaceRoot, originalUri.fsPath);
        const ext = kind === 'python' ? '.py' : '.jsx';
        const targetPath = path.join(root, `${relative}${ext}`);
        await fs.mkdir(path.dirname(targetPath), { recursive: true });
        await fs.writeFile(targetPath, content ?? '', 'utf8');
        const originalKey = originalUri.toString();
        const mapForDoc = this.virtualPaths.get(originalKey) || {};
        const previousUri = mapForDoc[kind];
        if (previousUri) {
            this.virtualIndex.delete(previousUri.toString());
        }
        const virtualUri = vscode.Uri.file(targetPath);
        mapForDoc[kind] = virtualUri;
        this.virtualPaths.set(originalKey, mapForDoc);
        this.virtualIndex.set(virtualUri.toString(), {
            original: originalUri,
            key: originalKey,
            kind,
        });
    }

    mapPosition(uri, position) {
        return (
            this._mapOriginalPositionForKind(uri, 'python', position) ||
            this._mapOriginalPositionForKind(uri, 'jsx', position)
        );
    }

    _mapOriginalPositionForKind(uri, kind, position) {
        const entry = this.cache.get(uri.toString());
        if (!entry) {
            return null;
        }
        const virtualLine = this._findVirtualLine(entry, kind, position.line + 1);
        if (virtualLine === -1) {
            return null;
        }
        const virtualUri = this._getVirtualUri(uri, kind);
        if (!virtualUri) {
            return null;
        }
        return {
            uri: virtualUri,
            position: new vscode.Position(virtualLine, position.character),
            kind,
        };
    }

    _findVirtualLine(entry, kind, sourceLine) {
        const info = entry[kind];
        if (!info || !Array.isArray(info.lineNumbers)) {
            return -1;
        }
        return info.lineNumbers.indexOf(sourceLine);
    }

    _getVirtualUri(originalUri, kind) {
        const map = this.virtualPaths.get(originalUri.toString());
        if (!map) {
            return null;
        }
        return map[kind] || null;
    }

    mapRangeFromVirtual(virtualUri, range) {
        if (!range) {
            return null;
        }
        const mapping = this._getVirtualMapping(virtualUri);
        if (!mapping) {
            return null;
        }
        const mappedRange = this._mapRangeWithMapping(mapping, range);
        if (!mappedRange) {
            return null;
        }
        return { uri: mapping.original, range: mappedRange };
    }

    async ensureVirtualFile(originalUri) {
        const map = this.virtualPaths.get(originalUri.toString());
        if (!map) {
            return;
        }
        for (const uri of Object.values(map)) {
            if (uri) {
                await vscode.workspace.openTextDocument(uri);
            }
        }
    }

    isVirtualUri(uri) {
        return this.virtualIndex.has(uri.toString());
    }

    translateDiagnostics(virtualUri, diagnostics) {
        const mapping = this._getVirtualMapping(virtualUri);
        if (!mapping) {
            return null;
        }
        const converted = [];
        for (const diagnostic of diagnostics || []) {
            const mappedRange = this._mapRangeWithMapping(mapping, diagnostic.range);
            if (!mappedRange) {
                continue;
            }
            const clone = new vscode.Diagnostic(mappedRange, diagnostic.message, diagnostic.severity);
            clone.code = diagnostic.code;
            clone.source = diagnostic.source;
            clone.tags = diagnostic.tags;
            clone.relatedInformation = diagnostic.relatedInformation
                ?.map((info) => this._mapRelatedInformation(info))
                .filter(Boolean);
            converted.push(clone);
        }
        return { original: mapping.original, diagnostics: converted };
    }

    _mapRelatedInformation(info) {
        if (!info) {
            return null;
        }
        const mapped = this.mapRangeFromVirtual(info.location.uri, info.location.range);
        const location = mapped ? new vscode.Location(mapped.uri, mapped.range) : info.location;
        return new vscode.DiagnosticRelatedInformation(location, info.message);
    }

    _mapRangeWithMapping(mapping, range) {
        if (!range) {
            return null;
        }
        const start = this._convertVirtualPosition(mapping, range.start);
        const end = this._convertVirtualPosition(mapping, range.end);
        if (!start || !end) {
            return null;
        }
        return new vscode.Range(start, end);
    }

    _convertVirtualPosition(mapping, position) {
        const entry = this.cache.get(mapping.key);
        if (!entry) {
            return null;
        }
        const info = entry[mapping.kind];
        if (!info || !Array.isArray(info.lineNumbers)) {
            return null;
        }
        const originalLine = info.lineNumbers[position.line];
        if (typeof originalLine !== 'number') {
            return null;
        }
        return new vscode.Position(Math.max(0, originalLine - 1), position.character);
    }

    _getVirtualMapping(uri) {
        return this.virtualIndex.get(uri.toString()) || null;
    }

    _removeVirtualPaths(originalKey) {
        const map = this.virtualPaths.get(originalKey);
        if (!map) {
            return;
        }
        for (const uri of Object.values(map)) {
            if (uri) {
                this.virtualIndex.delete(uri.toString());
            }
        }
        this.virtualPaths.delete(originalKey);
    }
}

module.exports = { activate, deactivate };
