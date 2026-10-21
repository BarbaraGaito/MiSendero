import { useId, useMemo } from "react";
import Svg, { Circle, ClipPath, Defs, G, Path, Rect, Text as SvgText } from "react-native-svg";
import type { BasicOfflineMap } from "../../services/basicOfflineMap";
import type { Coordinate } from "../../services/geoUtils";

const project = ([lat,lon]: Coordinate, zoom: number) => {
  const scale = 256 * 2 ** zoom, rad = lat * Math.PI / 180;
  return {x:(lon+180)/360*scale,y:(1-Math.log(Math.tan(rad)+1/Math.cos(rad))/Math.PI)/2*scale};
};
export function BasicMapLayer({map,center,zoom,width,height}: {
  map: BasicOfflineMap; center: Coordinate; zoom: number; width: number; height: number;
}) {
  const clipId = `basic-map-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const shapes = useMemo(() => {
    const origin = project(center,zoom);
    return map.features.map(feature => {
      const points = feature.points.map(p => { const q = project(p,zoom); return {x:q.x-origin.x+width/2,y:q.y-origin.y+height/2}; });
      const visible = Math.max(...points.map(p => p.x)) >= -80 && Math.min(...points.map(p => p.x)) <= width+80 &&
        Math.max(...points.map(p => p.y)) >= -80 && Math.min(...points.map(p => p.y)) <= height+80;
      return {feature,points,visible,path:points.map((p,i) => `${i ? 'L':'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')+(feature.closed?' Z':'')};
    }).filter(s => s.visible);
  },[map,center[0],center[1],zoom,width,height]);
  const origin = project(center,zoom);
  const northwest = project([map.bounds.north,map.bounds.west],zoom);
  const southeast = project([map.bounds.south,map.bounds.east],zoom);
  return <Svg testID="offline-basic-map" pointerEvents="none" width={width} height={height} style={{position:"absolute",left:0,top:0}}>
    <Rect x={0} y={0} width={width} height={height} fill="#e1e5e0" />
    <Rect x={northwest.x-origin.x+width/2} y={northwest.y-origin.y+height/2}
      width={southeast.x-northwest.x} height={southeast.y-northwest.y} fill="#f4f1e7" stroke="#a1b09c" strokeDasharray="6 5" />
    <Defs><ClipPath id={clipId}>
      <Rect x={northwest.x-origin.x+width/2} y={northwest.y-origin.y+height/2}
        width={southeast.x-northwest.x} height={southeast.y-northwest.y} />
    </ClipPath></Defs>
    <G clipPath={`url(#${clipId})`}>
    {shapes.filter(s => s.feature.kind !== 'place').map(({feature:f,path}) => <Path key={f.id} d={path}
      fill={f.closed ? f.kind === 'water' ? '#a8d4e5' : '#d1e2c6' : 'none'}
      stroke={f.kind === 'water' || f.kind === 'river' ? '#83bdcf' : f.kind === 'forest' ? '#c0d6b5' : f.kind === 'path' ? '#92734f' : '#ffffff'}
      strokeWidth={f.kind === 'road' ? 5 : f.kind === 'path' ? 1.5 : 2}
      strokeLinecap="round" strokeLinejoin="round" strokeDasharray={f.kind === 'path' ? '4 3' : undefined} />)}
    {shapes.filter(s => s.feature.name && (s.feature.kind === 'place' || zoom >= 14)).slice(0,45).map(({feature:f,points}) => {
      const p = points[Math.floor(points.length/2)];
      return <SvgText key={`label-${f.id}`} x={p.x+4} y={p.y-4} fontSize={f.kind === 'place' ? 11 : 9}
        fill={f.kind === 'water' || f.kind === 'river' ? '#356c86' : '#4c5d45'} stroke="#f4f1e7" strokeWidth={.3}>
        {f.name}
      </SvgText>;
    })}
    {shapes.filter(s => s.feature.kind === 'place').map(({feature:f,points}) =>
      <Circle key={f.id} cx={points[0].x} cy={points[0].y} r={2} fill="#4c5d45" />)}
    </G>
  </Svg>;
}
