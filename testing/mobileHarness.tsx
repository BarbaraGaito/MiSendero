import React from "react";
import { Image } from "react-native";
const renderer = require("react-test-renderer");
let mounted: any[] = [];
export const act = renderer.act;
export const flush = async () => { for (let step = 0; step < 12; step++) await Promise.resolve(); };
export async function mount(Component: React.ComponentType<any>, props = {}) {
  let tree: any;
  await act(async () => { tree = renderer.create(<Component {...props} />); await flush(); });
  mounted.push(tree);
  return tree;
}
const nodeText = (node: any): string => {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join(" ");
  return node?.children ? nodeText(node.children) : "";
};
export const text = (tree: any): string => nodeText(tree.toJSON());
export async function press(tree: any, label: string) {
  const node = tree.root.findAll((item: any) => typeof item.props.onPress === "function" && (item.props.accessibilityLabel === label || item.props.label === label || nodeText(item).replace(/\s+/g, " ").trim() === label))[0];
  if (!node) throw new Error(`Button not found: ${label}`);
  if (node.props.disabled || node.props.accessibilityState?.disabled) throw new Error(`Button disabled: ${label}`);
  await act(async () => { await node.props.onPress(); await flush(); });
}
beforeEach(() => { jest.clearAllMocks(); jest.spyOn(Image, "prefetch").mockResolvedValue(true); });
afterEach(async () => {
  for (const tree of mounted) await act(async () => tree.unmount());
  mounted = []; jest.restoreAllMocks();
});
