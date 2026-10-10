/**
 * The finale's section transition: night dissolving into paper along a
 * noise front with a warm burning edge. Raw WebGL1 (no three) -- one
 * full-screen triangle, one uniform, a frame only when progress changes.
 * Returns null when WebGL is unavailable; the caller falls back to an
 * opacity cross-fade.
 */

const VERT = `attribute vec2 p; varying vec2 uv; void main(){ uv = p*0.5+0.5; gl_Position = vec4(p,0.,1.); }`;

const FRAG = `
precision mediump float;
varying vec2 uv;
uniform float u_p;
uniform vec2 u_res;
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float n(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(h(i),h(i+vec2(1,0)),f.x), mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float v=0., a=.5; for(int i=0;i<5;i++){ v+=a*n(p); p*=2.03; a*=.5; } return v; }
void main(){
  vec2 q = uv * vec2(u_res.x/u_res.y, 1.) * 3.2;
  // the front rises from the bottom edge, like light coming up
  float field = fbm(q) * .55 + uv.y * .75;
  float t = u_p * 1.55 - .2;
  float edge = smoothstep(t - .06, t, field);
  float glow = smoothstep(t - .16, t - .04, field) * (1. - edge);
  vec3 night = mix(vec3(.043,.075,.106), vec3(.078,.125,.173), uv.y);
  vec3 paper = vec3(.945,.941,.918);
  vec3 ember = vec3(.91,.79,.66);
  vec3 col = mix(paper, night, edge);
  col = mix(col, ember, glow * .85);
  gl_FragColor = vec4(col, 1.);
}`;

export function createDawn(canvas: HTMLCanvasElement) {
  const gl = canvas.getContext("webgl", { antialias: false, premultipliedAlpha: false });
  if (!gl) return null;
  const sh = (type: number, src: string) => {
    const s = gl.createShader(type)!;
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return s;
  };
  const prog = gl.createProgram()!;
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const uP = gl.getUniformLocation(prog, "u_p");
  const uRes = gl.getUniformLocation(prog, "u_res");

  let p = 0;
  let raf = 0;
  const draw = () => {
    raf = 0;
    gl.uniform1f(uP, p);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const resize = () => {
    // Half resolution is plenty for a soft noise front and keeps fill cheap.
    const dpr = Math.min(window.devicePixelRatio, 2) * 0.5;
    canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr));
    canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr));
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(uRes, canvas.width, canvas.height);
    draw();
  };
  resize();
  window.addEventListener("resize", resize);

  return {
    set(v: number) {
      if (Math.abs(v - p) < 0.001) return;
      p = v;
      if (!raf) raf = requestAnimationFrame(draw);
    },
    dispose() {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}
