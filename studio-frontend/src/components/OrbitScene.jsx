import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/** A genuinely interactive 3D evidence constellation, generated from live record counts.
 * Camera and orbit rotate with pointer. Canvas is decorative; all source actions remain
 * keyboard-accessible in standard React controls outside the scene. */
export default function OrbitScene({ counts = {} }) {
  const hostRef = useRef(null)
  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    let frame = 0
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 70)
    camera.position.set(0, 0, 9.5)
    const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true, powerPreference:'high-performance'})
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    const world = new THREE.Group(); scene.add(world)
    const coreGeo = new THREE.IcosahedronGeometry(1.23, 5)
    const coreMat = new THREE.MeshPhysicalMaterial({color:0x3e78a9, roughness:0.26, metalness:0.46, transparent:true, opacity:0.54, emissive:0x173d65, emissiveIntensity:0.58, flatShading:false})
    const core = new THREE.Mesh(coreGeo,coreMat);world.add(core)
    const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(1.32,2),new THREE.MeshBasicMaterial({color:0x6fe3dd,wireframe:true,transparent:true,opacity:0.19}))
    world.add(wire)
    const inner = new THREE.Mesh(new THREE.IcosahedronGeometry(0.73,3),new THREE.MeshBasicMaterial({color:0xab9cf7,wireframe:true,transparent:true,opacity:0.26}))
    world.add(inner)
    const ringMaterial = new THREE.MeshBasicMaterial({color:0x526aa1,side:THREE.DoubleSide,transparent:true,opacity:0.24})
    const rings = []
    ;[[2.05,0.27,0.12],[2.65,-0.62,0.35],[3.23,0.44,-0.1]].forEach(([r,x,y])=>{
      const ring=new THREE.Mesh(new THREE.TorusGeometry(r,0.009,4,140),ringMaterial)
      ring.rotation.set(x,y,0.18);world.add(ring);rings.push(ring)
    })
    const colors=[0x62efcf,0xb2a0ff,0xf8c38a,0x91b7ff,0x76dcd7]
    const byType=Object.entries(counts).filter(([k,v])=>v>0 && k!=='notification').slice(0,5)
    const num = Math.max(16, Math.min(32, byType.reduce((n,[,v])=>n+Math.ceil(Math.sqrt(v)),0)))
    const nodeGeo = new THREE.SphereGeometry(0.055,12,10)
    const edges=[]
    for (let i=0;i<num;i++) {
      const a=(i/num)*Math.PI*2
      const b=0.32*Math.sin(i*2.39)+0.25*Math.cos(i)
      const radius=2.16 + (i%4)*0.28
      const x=Math.cos(a)*radius
      const y=Math.sin(a*1.6)*radius*0.43 + Math.sin(b)*0.33
      const z=Math.sin(a)*radius*0.68
      const node=new THREE.Mesh(nodeGeo,new THREE.MeshBasicMaterial({color:colors[i%colors.length]}))
      node.position.set(x,y,z)
      node.scale.setScalar(i%6===0?1.8:1.1)
      world.add(node)
      if (i%2===0) {
        const pts=[new THREE.Vector3(x,y,z), new THREE.Vector3(x*0.35,y*0.35,z*0.35)]
        const g=new THREE.BufferGeometry().setFromPoints(pts)
        const line=new THREE.Line(g,new THREE.LineBasicMaterial({color:colors[i%colors.length], transparent:true,opacity:0.13}))
        world.add(line);edges.push(line)
      }
    }
    const dust = new THREE.BufferGeometry()
    const dustPositions = new Float32Array(170*3)
    for(let i=0;i<170;i++) {
      const a=i*2.39996, z=(i%31)/15-1, r=4.4+((i*17)%23)/25
      dustPositions[3*i]=Math.cos(a)*r*Math.sqrt(1-z*z)
      dustPositions[3*i+1]=Math.sin(a)*r*Math.sqrt(1-z*z)
      dustPositions[3*i+2]=z*r
    }
    dust.setAttribute('position',new THREE.BufferAttribute(dustPositions,3))
    const particles=new THREE.Points(dust,new THREE.PointsMaterial({color:0x7890af,size:0.022,transparent:true,opacity:0.47}))
    world.add(particles)
    const lights=[new THREE.PointLight(0x79f4e0,13,10),new THREE.PointLight(0xaa80ff,10,8)]
    lights[0].position.set(2.5,2.5,3); lights[1].position.set(-3,-1,2); lights.forEach(l=>scene.add(l))
    scene.add(new THREE.AmbientLight(0x4d7b9c,1.9))

    const resize=()=>{
      const w=Math.max(el.clientWidth,1),h=Math.max(el.clientHeight,1)
      renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()
    }
    const observer=new ResizeObserver(resize);observer.observe(el);resize()
    const target={x:0,y:0}
    const pointer=(event)=>{
      const rect=el.getBoundingClientRect()
      target.x=((event.clientY-rect.top)/rect.height-.5)*0.37
      target.y=((event.clientX-rect.left)/rect.width-.5)*0.55
    }
    el.addEventListener('pointermove',pointer)
    const clock=new THREE.Clock()
    const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches
    function animate(){
      frame=requestAnimationFrame(animate)
      const t=clock.getElapsedTime()
      world.rotation.x += (target.x-world.rotation.x)*0.028
      world.rotation.y += (target.y-world.rotation.y)*0.022
      if(!reduce){core.rotation.y=t*0.11;inner.rotation.y=-t*0.17;wire.rotation.y=t*0.06; world.rotation.z=Math.sin(t*0.14)*0.045}
      renderer.render(scene,camera)
    }
    animate()
    return ()=>{
      cancelAnimationFrame(frame);observer.disconnect();el.removeEventListener('pointermove',pointer)
      scene.traverse(object=>{
        if(object.geometry)object.geometry.dispose()
        if(object.material){(Array.isArray(object.material)?object.material:[object.material]).forEach(mat=>mat.dispose())}
      })
      renderer.dispose()
      if(renderer.domElement.parentElement===el)el.removeChild(renderer.domElement)
    }
  },[JSON.stringify(counts)])
  return <div className="orbit-scene" aria-hidden="true" ref={hostRef}/>
}
