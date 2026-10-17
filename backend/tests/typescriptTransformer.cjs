const ts = require("typescript");
module.exports = { process(source, filename) {
  const result = ts.transpileModule(source, { fileName: filename, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true,
    sourceMap: true, inlineSources: true,
  } });
  return { code: result.outputText, map: result.sourceMapText };
} };
