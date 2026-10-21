import { Asset } from "expo-asset";
import type { ExpoWebGLRenderingContext } from "expo-gl";
import { Image, Platform } from "react-native";
import * as THREE from "three";

export function createTerrainRenderer(gl: ExpoWebGLRenderingContext) {
  const version = String(gl.getParameter(gl.VERSION));
  if (!/^(WebGL 2\.|OpenGL ES 3\.)/.test(version)) {
    throw new Error("El relieve 3D requiere WebGL 2 / OpenGL ES 3.");
  }

  // Expo GL's WebGL2 context also inherits from WebGLRenderingContext.
  // Three r166 rejects it when passed via `context`, even though it is GL2.
  // Let Three request the already-validated context through its canvas API.
  // Do not mutate global constructors or pretend a WebGL1 GPU supports GL2.
  const canvas = {
    width: gl.drawingBufferWidth,
    height: gl.drawingBufferHeight,
    style: {},
    getContext: (name: string) => name === "webgl2" ? gl : null,
    addEventListener: (type: string, listener: EventListener) => gl.canvas?.addEventListener?.(type, listener),
    removeEventListener: (type: string, listener: EventListener) => gl.canvas?.removeEventListener?.(type, listener),
  } as unknown as HTMLCanvasElement;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(1);
  renderer.setSize(gl.drawingBufferWidth || 1, gl.drawingBufferHeight || 1, false);
  renderer.setClearColor("#DCEFF7");
  return renderer;
}

export async function loadTerrainTexture(url: string): Promise<THREE.Texture> {
  if (Platform.OS === "web") {
    return new THREE.TextureLoader().setCrossOrigin("anonymous").loadAsync(url);
  }
  const asset = await Asset.fromURI(url).downloadAsync();
  const uri = asset.localUri;
  if (!uri) throw new Error("No se pudo descargar la imagen del terreno.");
  const size = asset.width && asset.height ? { width: asset.width, height: asset.height }
    : await Image.getSize(uri);
  // Expo GL accepts an asset with localUri as texImage2D's native data source.
  // DataTexture makes Three forward that source to GL instead of using DOM APIs.
  const texture = new THREE.DataTexture();
  texture.image = { data: { localUri: uri }, ...size } as unknown as THREE.DataTexture["image"];
  texture.flipY = true;
  texture.needsUpdate = true;
  return texture;
}
