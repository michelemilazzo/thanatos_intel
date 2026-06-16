// Converte testo semplice (stdin) nello stato Yjs base64url che l'editor
// collaborativo di Frappe Drive (Tiptap Collaboration, fragment "default")
// legge dal campo Drive Document.content. Necessario perché Tiptap-Collaboration
// ignora il contenuto iniziale: il testo va seminato nel doc Yjs.
//
// Uso: node pm2yjs.cjs <drive_frontend_dir>   (testo su stdin -> base64url su stdout)
// I moduli (yjs/y-prosemirror/prosemirror-model) sono risolti dal node_modules
// del frontend Drive passato come argomento (pnpm).
const path = require("path");
const fe = process.argv[2];
const feNM = path.join(fe, "node_modules");

const Y = require(require.resolve("yjs", { paths: [feNM] }));
const ypmPath = require.resolve("y-prosemirror", { paths: [feNM] });
const { prosemirrorToYDoc } = require(ypmPath);
const { Schema } = require(require.resolve("prosemirror-model", { paths: [path.dirname(ypmPath)] }));

const schema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: { group: "block", content: "inline*", parseDOM: [{ tag: "p" }], toDOM() { return ["p", 0]; } },
    text: { group: "inline" },
  },
  marks: {},
});

let text = "";
process.stdin.on("data", (d) => (text += d));
process.stdin.on("end", () => {
  const lines = text.replace(/\r/g, "").split("\n");
  const paras = lines.map((l) =>
    l.length ? schema.node("paragraph", null, schema.text(l)) : schema.node("paragraph"));
  const doc = schema.node("doc", null, paras);
  const ydoc = prosemirrorToYDoc(doc, "default");
  const upd = Y.encodeStateAsUpdate(ydoc);
  process.stdout.write(
    Buffer.from(upd).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""));
});
