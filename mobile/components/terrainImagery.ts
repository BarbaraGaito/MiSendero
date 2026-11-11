import * as THREE from "three";
import type { TerrainGridBounds } from "../../services/terrainElevation";
import { loadTerrainTexture } from "./terrainGraphics";
import { TERRAIN_SCENE_HALF_SIZE, TerrainSceneModel } from "./terrainSceneModel";

const DETAIL_SIDE_METERS = 384;
const DETAIL_IMAGE_PIXELS = 1024;

function getSatelliteTextureUrl({ north, south, east, west }: TerrainGridBounds, pixels: number) {
  // Export Map adjusts the extent to match the image's aspect ratio.
  const span = Math.max(east - west, north - south);
  const width = Math.max(1, Math.round(pixels * (east - west) / span));
  const height = Math.max(1, Math.round(pixels * (north - south) / span));
  const params = new URLSearchParams({
    bbox: `${west},${south},${east},${north}`,
    bboxSR: "4326",
    imageSR: "4326",
    size: `${width},${height}`,
    format: "jpg",
    transparent: "false",
    f: "image",
  });
  return `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?${params.toString()}`;
}

function prepareTexture(texture: THREE.Texture, anisotropy: number) {
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = anisotropy;
  texture.generateMipmaps = true;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
}

function addTerrainDetailShader(material: THREE.MeshStandardMaterial) {
  const detailMap = { value: null as THREE.Texture | null };
  const detailBounds = { value: new THREE.Vector4(0, 0, 1, 1) };
  const detailEnabled = { value: false };
  material.onBeforeCompile = (shader) => {
    shader.uniforms.terrainDetailMap = detailMap;
    shader.uniforms.terrainDetailBounds = detailBounds;
    shader.uniforms.terrainDetailEnabled = detailEnabled;
    shader.vertexShader = shader.vertexShader
      .replace("#include <uv_pars_vertex>", "#include <uv_pars_vertex>\nvarying vec2 vTerrainUv;")
      .replace("#include <uv_vertex>", "#include <uv_vertex>\nvTerrainUv = uv;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <map_pars_fragment>", `#include <map_pars_fragment>
        varying vec2 vTerrainUv;
        uniform sampler2D terrainDetailMap;
        uniform vec4 terrainDetailBounds;
        uniform bool terrainDetailEnabled;
      `)
      .replace("#include <map_fragment>", `#include <map_fragment>
        if (terrainDetailEnabled) {
          vec2 detailUv = (vTerrainUv - terrainDetailBounds.xy) / terrainDetailBounds.zw;
          vec2 edge = min(detailUv, 1.0 - detailUv);
          float blend = smoothstep(0.0, 0.15, min(edge.x, edge.y));
          diffuseColor.rgb = mix(diffuseColor.rgb, texture2D(terrainDetailMap, detailUv).rgb, blend);
        }
      `);
  };
  return { detailMap, detailBounds, detailEnabled };
}

export function createTerrainImagery(
  material: THREE.MeshStandardMaterial,
  model: TerrainSceneModel,
  maxAnisotropy: number,
  navigationMode: boolean,
  onBaseLoad: () => void
) {
  const { bounds, sideLengthMeters } = model.grid;
  const detail = navigationMode ? addTerrainDetailShader(material) : null;
  const anisotropy = Math.max(1, Math.min(navigationMode ? 16 : 8, maxAnisotropy));
  let disposed = false;

  void loadTerrainTexture(getSatelliteTextureUrl(bounds, 2048)).then((texture) => {
    if (disposed) {
      texture.dispose();
      return;
    }
    prepareTexture(texture, anisotropy);
    material.map = texture;
    material.vertexColors = false;
    material.color.set("#FFFFFF");
    material.roughness = 0.94;
    material.needsUpdate = true;
    onBaseLoad();
  }).catch(() => undefined); // El tinte por altura sigue visible si falla la imagen.

  const detailSize = Math.min(1, DETAIL_SIDE_METERS / sideLengthMeters);
  const halfSize = detailSize / 2;
  const centerStep = detailSize / 3;
  let area: { url: string; centerU: number; centerV: number } | null = null;
  let pending = false;
  let lastRequestedUrl: string | null = null;
  let displayedUrl: string | null = null;

  const loadDetail = async () => {
    const target = area;
    if (!detail || !target || disposed || pending || target.url === lastRequestedUrl || target.url === displayedUrl) return;
    pending = true;
    lastRequestedUrl = target.url;
    try {
      const texture = await loadTerrainTexture(target.url);
      if (disposed || area?.url !== target.url) {
        texture.dispose();
        return;
      }
      prepareTexture(texture, anisotropy);
      detail.detailMap.value?.dispose();
      detail.detailMap.value = texture;
      detail.detailBounds.value.set(target.centerU - halfSize, target.centerV - halfSize, detailSize, detailSize);
      detail.detailEnabled.value = true;
      displayedUrl = target.url;
    } catch {
      // Conserva la imagen general y el último detalle que se pudo cargar.
    } finally {
      pending = false;
      void loadDetail();
    }
  };

  return {
    updatePosition(x: number, z: number) {
      if (!detail || disposed) return;
      const u = (x + TERRAIN_SCENE_HALF_SIZE) / (2 * TERRAIN_SCENE_HALF_SIZE);
      const v = (TERRAIN_SCENE_HALF_SIZE - z) / (2 * TERRAIN_SCENE_HALF_SIZE);
      if (area && Math.max(Math.abs(u - area.centerU), Math.abs(v - area.centerV)) <= detailSize / 4) return;

      // Solicita áreas fijas del mapa, con margen para el ruido del GPS.
      const snapCenter = (value: number) =>
        Math.max(halfSize, Math.min(1 - halfSize, Math.round(value / centerStep) * centerStep));
      const centerU = snapCenter(u);
      const centerV = snapCenter(v);
      const longitudeAt = (uv: number) => bounds.west + uv * (bounds.east - bounds.west);
      const latitudeAt = (uv: number) => bounds.south + uv * (bounds.north - bounds.south);
      const url = getSatelliteTextureUrl({
        west: longitudeAt(centerU - halfSize),
        east: longitudeAt(centerU + halfSize),
        south: latitudeAt(centerV - halfSize),
        north: latitudeAt(centerV + halfSize),
      }, DETAIL_IMAGE_PIXELS);
      area = { url, centerU, centerV };
      void loadDetail();
    },
    dispose() {
      disposed = true;
      detail?.detailMap.value?.dispose();
    },
  };
}
