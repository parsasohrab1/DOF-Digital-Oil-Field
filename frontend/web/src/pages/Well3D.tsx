import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, Text, Html, Environment } from '@react-three/drei'
import * as THREE from 'three'
import { useQuery, useMutation } from '@tanstack/react-query'
import { well3DAPI, digitalTwinAPI } from '../api/services'
import {
  FIELD,
  DEHLORAN_WELLS,
  STATUS_COLOR,
  STATUS_LABEL_FA,
  getDehloranLiveState,
  buildDehloranWell3DData,
  buildAllDehloranWells3D,
} from '../data/dehloranField'
import './Well3D.css'

interface DepthData {
  depth: number
  pressure: number
  temperature: number
  flowRate: number
  status: 'normal' | 'warning' | 'critical'
}

interface CasingData {
  depth: number
  outerDiameter: number // inches
  innerDiameter: number // inches
  type: 'conductor' | 'surface' | 'intermediate' | 'production'
  cementThickness: number // inches
}

interface BOPData {
  type: string
  pressureRating: number // psi
  stackHeight: number // meters
  status: 'open' | 'closed' | 'maintenance'
}

interface WellheadEquipment {
  christmasTree: {
    height: number
    width: number
    status: 'open' | 'closed'
  }
  masterValve: {
    position: number // 0-100%
    status: 'open' | 'closed'
  }
  wingValve: {
    position: number
    status: 'open' | 'closed'
  }
  chokeValve: {
    position: number
    status: 'open' | 'closed'
  }
  pressureGauges: Array<{
    name: string
    value: number
    unit: string
  }>
  flowMeter: {
    flowRate: number
    unit: string
  }
}

interface Well3DData {
  wellName: string
  totalDepth: number
  depthData: DepthData[]
  surfaceData: {
    wellheadPressure: number
    wellheadTemperature: number
    flowRate: number
  }
  trajectory?: {
    md_points: Array<{ md: number; inclination: number; azimuth: number }>
  }
  riskZones?: Array<{ name: string; fromDepth: number; toDepth: number; severity: 'warning' | 'critical' }>
  bop?: BOPData
  casings?: CasingData[]
  wellheadEquipment?: WellheadEquipment
}

function valveStatusFa(s: string) {
  if (s === 'open') return 'باز'
  if (s === 'closed') return 'بسته'
  if (s === 'maintenance') return 'در تعمیر'
  return s
}

function depthStatusFa(s: string) {
  if (s === 'normal') return 'نرمال'
  if (s === 'warning') return 'هشدار'
  if (s === 'critical') return 'بحرانی'
  return s
}

function casingTypeFa(t: string) {
  if (t === 'conductor') return 'هادی'
  if (t === 'surface') return 'سطحی'
  if (t === 'intermediate') return 'میانی'
  if (t === 'production') return 'تولیدی'
  return t
}

function riskLevelFa(s: string) {
  if (s === 'elevated') return 'بالا'
  if (s === 'normal') return 'عادی'
  if (s === 'high') return 'بالا'
  if (s === 'critical') return 'بحرانی'
  return s
}

// Wellhead Equipment Component - تجهیزات سر چاهی
function WellheadEquipment({ equipment, wellName }: { equipment?: WellheadEquipment; wellName: string }) {
  const [hovered, setHovered] = useState<string | null>(null)
  
  const defaultEquipment: WellheadEquipment = equipment || {
    christmasTree: {
      height: 2.5,
      width: 1.2,
      status: 'open'
    },
    masterValve: {
      position: 100,
      status: 'open'
    },
    wingValve: {
      position: 75,
      status: 'open'
    },
    chokeValve: {
      position: 50,
      status: 'open'
    },
    pressureGauges: [
      { name: 'Wellhead Pressure', value: 2500, unit: 'psi' },
      { name: 'Tubing Pressure', value: 2300, unit: 'psi' },
      { name: 'Casing Pressure', value: 500, unit: 'psi' }
    ],
    flowMeter: {
      flowRate: 850,
      unit: 'bbl/day'
    }
  }

  const bopHeight = 3.5
  const wellheadBaseY = bopHeight + 0.5

  return (
    <group position={[0, wellheadBaseY, 0]}>
      {/* Christmas Tree - درخت کریسمس */}
      <group
        onPointerOver={() => setHovered('christmasTree')}
        onPointerOut={() => setHovered(null)}
      >
        {/* Main Tree Body */}
        <mesh position={[0, defaultEquipment.christmasTree.height / 2, 0]}>
          <boxGeometry args={[defaultEquipment.christmasTree.width, defaultEquipment.christmasTree.height, defaultEquipment.christmasTree.width]} />
          <meshStandardMaterial 
            color={defaultEquipment.christmasTree.status === 'open' ? '#4169e1' : '#8b0000'}
            metalness={0.8}
            roughness={0.2}
          />
        </mesh>

        {/* Tree Branches (Valve Manifold) */}
        {[0, 1, 2].map((i) => {
          const angle = (i / 3) * Math.PI * 2
          const x = Math.cos(angle) * 0.6
          const z = Math.sin(angle) * 0.6
          return (
            <mesh key={i} position={[x, defaultEquipment.christmasTree.height * 0.7, z]}>
              <cylinderGeometry args={[0.1, 0.1, 0.4, 16]} />
              <meshStandardMaterial color="#333333" metalness={0.9} roughness={0.1} />
            </mesh>
          )
        })}

        {/* Master Valve */}
        <mesh position={[0, defaultEquipment.christmasTree.height * 0.3, 0]}>
          <cylinderGeometry args={[0.15, 0.15, 0.3, 16]} />
          <meshStandardMaterial 
            color={defaultEquipment.masterValve.status === 'open' ? '#00ff00' : '#ff0000'}
            metalness={0.9}
            roughness={0.1}
          />
        </mesh>

        {/* Wing Valves */}
        {[0, 1].map((i) => {
          const angle = (i / 2) * Math.PI
          const x = Math.cos(angle) * 0.5
          const z = Math.sin(angle) * 0.5
          return (
            <mesh key={i} position={[x, defaultEquipment.christmasTree.height * 0.5, z]}>
              <cylinderGeometry args={[0.12, 0.12, 0.25, 16]} />
              <meshStandardMaterial 
                color={defaultEquipment.wingValve.status === 'open' ? '#00ff00' : '#ff0000'}
                metalness={0.9}
                roughness={0.1}
              />
            </mesh>
          )
        })}

        {/* Choke Valve */}
        <mesh position={[0.6, defaultEquipment.christmasTree.height * 0.5, 0]}>
          <cylinderGeometry args={[0.18, 0.18, 0.3, 16]} />
          <meshStandardMaterial 
            color="#ffaa00"
            metalness={0.8}
            roughness={0.2}
          />
          {/* Choke Position Indicator */}
          <mesh position={[0, 0.2, 0]} rotation={[0, 0, (defaultEquipment.chokeValve.position / 100) * Math.PI * 2]}>
            <boxGeometry args={[0.05, 0.15, 0.05]} />
            <meshStandardMaterial color="#ffff00" />
          </mesh>
        </mesh>

        {/* Pressure Gauges */}
        {defaultEquipment.pressureGauges.map((gauge, i) => {
          const angle = (i / defaultEquipment.pressureGauges.length) * Math.PI * 2
          const x = Math.cos(angle) * 0.8
          const z = Math.sin(angle) * 0.8
          return (
            <group key={i} position={[x, defaultEquipment.christmasTree.height * 0.8, z]}>
              <mesh>
                <cylinderGeometry args={[0.1, 0.1, 0.1, 16]} />
                <meshStandardMaterial color="#ffffff" metalness={0.7} roughness={0.3} />
              </mesh>
              <Text
                position={[0, 0.15, 0]}
                fontSize={0.08}
                color="#ffffff"
                anchorX="center"
                anchorY="middle"
              >
                {gauge.value.toFixed(0)}
              </Text>
            </group>
          )
        })}

        {/* Flow Meter */}
        <group position={[0, defaultEquipment.christmasTree.height + 0.3, 0]}>
          <mesh>
            <boxGeometry args={[0.3, 0.2, 0.2]} />
            <meshStandardMaterial color="#00ffff" metalness={0.6} roughness={0.4} />
          </mesh>
          <Text
            position={[0, 0, 0]}
            fontSize={0.1}
            color="#000000"
            anchorX="center"
            anchorY="middle"
          >
            {defaultEquipment.flowMeter.flowRate.toFixed(0)}
          </Text>
        </group>

        {hovered === 'christmasTree' && (
          <Html distanceFactor={10}>
            <div className="sensor-tooltip" dir="rtl">
              <h4>درخت کریسمس — {wellName}</h4>
              <p>شیر اصلی: {valveStatusFa(defaultEquipment.masterValve.status)} ({defaultEquipment.masterValve.position}%)</p>
              <p>شیر بال: {valveStatusFa(defaultEquipment.wingValve.status)} ({defaultEquipment.wingValve.position}%)</p>
              <p>شیر کنترل جریان: {valveStatusFa(defaultEquipment.chokeValve.status)} ({defaultEquipment.chokeValve.position}%)</p>
              <p>دبی: {defaultEquipment.flowMeter.flowRate} {defaultEquipment.flowMeter.unit}</p>
            </div>
          </Html>
        )}
      </group>
    </group>
  )
}

// BOP Component - Blow Out Preventer
function BOP({ bopData }: { bopData?: BOPData }) {
  const [hovered, setHovered] = useState(false)
  
  const defaultBOP: BOPData = bopData || {
    type: 'جلوگیری‌کننده حلقوی از فوران',
    pressureRating: 10000,
    stackHeight: 3.5,
    status: 'open'
  }

  const getColor = () => {
    switch (defaultBOP.status) {
      case 'closed': return '#ff0000'
      case 'maintenance': return '#ffaa00'
      default: return '#00ff00'
    }
  }

  return (
    <group position={[0, defaultBOP.stackHeight / 2 + 0.5, 0]}>
      {/* Main BOP Stack */}
      <mesh
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <cylinderGeometry args={[0.6, 0.6, defaultBOP.stackHeight, 32]} />
        <meshStandardMaterial 
          color={getColor()}
          metalness={0.9}
          roughness={0.1}
          emissive={getColor()}
          emissiveIntensity={0.2}
        />
      </mesh>

      {/* BOP Stack Layers */}
      {[0, 1, 2].map((layer) => (
        <mesh
          key={layer}
          position={[0, (layer - 1) * 1.1, 0]}
        >
          <cylinderGeometry args={[0.65, 0.65, 0.3, 32]} />
          <meshStandardMaterial 
            color="#333333"
            metalness={0.95}
            roughness={0.05}
          />
        </mesh>
      ))}

      {/* BOP Control Lines */}
      {[0, 1, 2, 3].map((i) => {
        const angle = (i / 4) * Math.PI * 2
        return (
          <mesh
            key={i}
            position={[
              Math.cos(angle) * 0.7,
              defaultBOP.stackHeight / 2,
              Math.sin(angle) * 0.7
            ]}
          >
            <cylinderGeometry args={[0.05, 0.05, 0.5, 8]} />
            <meshStandardMaterial color="#ffaa00" />
          </mesh>
        )
      })}

      {hovered && (
        <Html distanceFactor={10}>
          <div className="sensor-tooltip" dir="rtl">
            <h4>جلوگیری‌کننده از فوران</h4>
            <p>نوع: {defaultBOP.type}</p>
            <p>رتبه فشار: {defaultBOP.pressureRating.toLocaleString()} psi</p>
            <p>ارتفاع مجموعه: {defaultBOP.stackHeight.toFixed(1)} m</p>
            <p>وضعیت: {valveStatusFa(defaultBOP.status)}</p>
          </div>
        </Html>
      )}
    </group>
  )
}

// Casing Component - نمایش لوله‌های Casing
function Casing({ casing }: { casing: CasingData }) {
  const [hovered, setHovered] = useState(false)
  const radius = casing.outerDiameter / 24 // Convert inches to meters (approximate)
  const innerRadius = casing.innerDiameter / 24
  const casingLength = casing.depth
  const cementRadius = radius + casing.cementThickness / 24

  const getCasingColor = () => {
    switch (casing.type) {
      case 'conductor': return '#8b4513'
      case 'surface': return '#4169e1'
      case 'intermediate': return '#32cd32'
      case 'production': return '#ff6347'
      default: return '#808080'
    }
  }

  return (
    <group position={[0, -casingLength / 2, 0]}>
      {/* Cement Layer (outside casing) */}
      <mesh>
        <cylinderGeometry args={[cementRadius, cementRadius, casingLength, 32]} />
        <meshStandardMaterial 
          color="#c0c0c0"
          metalness={0.3}
          roughness={0.8}
          opacity={0.6}
          transparent
        />
      </mesh>

      {/* Outer Casing */}
      <mesh
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <cylinderGeometry args={[radius, radius, casingLength, 32]} />
        <meshStandardMaterial 
          color={getCasingColor()}
          metalness={0.7}
          roughness={0.3}
        />
      </mesh>

      {/* Inner Casing (hollow - shows previous casing or wellbore) */}
      <mesh>
        <cylinderGeometry args={[innerRadius, innerRadius, casingLength, 32]} />
        <meshStandardMaterial 
          color="#1a1a1a"
          side={THREE.BackSide}
        />
      </mesh>

      {/* Casing Label */}
      <Text
        position={[cementRadius + 0.3, -casingLength / 2, 0]}
        fontSize={0.15}
        color="#ffffff"
        anchorX="left"
        anchorY="middle"
      >
        {casing.type.toUpperCase()}
      </Text>

      {/* Size Label */}
      <Text
        position={[cementRadius + 0.3, -casingLength / 2 + 0.2, 0]}
        fontSize={0.12}
        color="#ffff00"
        anchorX="left"
        anchorY="middle"
      >
        {casing.outerDiameter}" OD / {casing.innerDiameter}" ID
      </Text>

      {/* Cement Label */}
      <Text
        position={[cementRadius + 0.3, -casingLength / 2 + 0.4, 0]}
        fontSize={0.1}
        color="#c0c0c0"
        anchorX="left"
        anchorY="middle"
      >
        Cement: {casing.cementThickness}" ({casing.cementThickness * 25.4}mm)
      </Text>

      {hovered && (
        <Html distanceFactor={10}>
          <div className="sensor-tooltip" dir="rtl">
            <h4>غلاف: {casingTypeFa(casing.type)}</h4>
            <p>عمق: ۰ – {casing.depth.toFixed(1)} m</p>
            <p>قطر خارجی: {casing.outerDiameter}" ({casing.outerDiameter * 25.4}mm)</p>
            <p>قطر داخلی: {casing.innerDiameter}" ({casing.innerDiameter * 25.4}mm)</p>
            <p>ضخامت سیمان: {casing.cementThickness}" ({casing.cementThickness * 25.4}mm)</p>
            <p>ضخامت دیواره: {((casing.outerDiameter - casing.innerDiameter) / 2).toFixed(2)}"</p>
          </div>
        </Html>
      )}
    </group>
  )
}

// Wellbore component - نمایش لوله چاه
function Wellbore({ depth, data, casings }: { depth: number; data: DepthData[]; casings?: CasingData[] }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const segments = 50
  const radius = 0.3

  // Create color based on status
  const getColor = (status: string) => {
    switch (status) {
      case 'critical': return '#ff0000'
      case 'warning': return '#ffaa00'
      default: return '#4a90e2'
    }
  }

  // Create geometry for wellbore
  const points: THREE.Vector3[] = []
  for (let i = 0; i <= segments; i++) {
    const y = -(i / segments) * depth
    points.push(new THREE.Vector3(0, y, 0))
  }

  return (
    <group>
      {/* Render casings first (they're larger, nested from outside to inside) */}
      {casings && casings.map((casing, index) => (
        <Casing key={index} casing={casing} />
      ))}

      {/* Main wellbore cylinder (only if no casings or as inner liner) */}
      {(!casings || casings.length === 0) && (
        <mesh ref={meshRef} position={[0, -depth / 2, 0]}>
          <cylinderGeometry args={[radius, radius, depth, 32]} />
          <meshStandardMaterial color="#2c3e50" metalness={0.3} roughness={0.7} />
        </mesh>
      )}

      {/* Depth segments with status colors (inside casings) */}
      {data.map((segment, index) => {
        const segmentDepth = depth / data.length
        const yPosition = -(index * segmentDepth + segmentDepth / 2)
        const color = getColor(segment.status)
        const innerRadius = casings && casings.length > 0 
          ? (casings[casings.length - 1]?.innerDiameter || 0) / 24 * 0.8
          : radius * 0.8

        return (
          <mesh
            key={index}
            position={[0, yPosition, 0]}
          >
            <cylinderGeometry args={[innerRadius, innerRadius, segmentDepth, 16]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.3}
              metalness={0.5}
              roughness={0.5}
              transparent
              opacity={0.7}
            />
          </mesh>
        )
      })}
    </group>
  )
}

// Sensor point component - نمایش نقاط سنسور
function SensorPoint({
  position,
  depth,
  data,
  label
}: {
  position: [number, number, number]
  depth: number
  data: DepthData
  label: string
}) {
  const [hovered, setHovered] = useState(false)
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.01
    }
  })

  const getColor = () => {
    switch (data.status) {
      case 'critical': return '#ff0000'
      case 'warning': return '#ffaa00'
      default: return '#00ff00'
    }
  }

  return (
    <group position={position}>
      <mesh
        ref={meshRef}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
        scale={hovered ? 1.5 : 1}
      >
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshStandardMaterial
          color={getColor()}
          emissive={getColor()}
          emissiveIntensity={0.5}
        />
      </mesh>
      {hovered && (
        <Html distanceFactor={10}>
          <div className="sensor-tooltip" dir="rtl">
            <h4>{label}</h4>
            <p>عمق: {depth.toFixed(1)} m</p>
            <p>فشار: {data.pressure.toFixed(2)} psi</p>
            <p>دما: {data.temperature.toFixed(1)} °C</p>
            <p>دبی: {data.flowRate.toFixed(2)} bbl/day</p>
            <p>وضعیت: {depthStatusFa(data.status)}</p>
          </div>
        </Html>
      )}
    </group>
  )
}

// Depth labels - برچسب‌های عمق
function DepthLabels({ depth, segments }: { depth: number; segments: number }) {
  const labels = []
  for (let i = 0; i <= segments; i++) {
    const y = -(i / segments) * depth
    const depthValue = (i / segments) * depth

    labels.push(
      <Text
        key={i}
        position={[0.8, y, 0]}
        fontSize={0.2}
        color="#ffffff"
        anchorX="left"
        anchorY="middle"
      >
        {depthValue.toFixed(0)}m
      </Text>
    )
  }
  return <group>{labels}</group>
}

// Multiple Wells Scene - نمایش چند چاه
function MultipleWellsScene({ wellsData, wells }: { wellsData: Record<string, Well3DData | null>; wells: string[] }) {
  const controlsRef = useRef<any>(null)
  const spacing = 12 // فاصله بین چاه‌های دهلران (۴×۴)

  return (
    <>
      <PerspectiveCamera makeDefault position={[40, 28, 40]} fov={50} />
      <OrbitControls
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={10}
        maxDistance={120}
      />

      {/* Lighting */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <pointLight position={[-10, 10, -10]} intensity={0.5} />

      {/* Ground plane - میدان دهلران */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.1, 0]}>
        <planeGeometry args={[120, 120]} />
        <meshStandardMaterial color="#3a5f3a" />
      </mesh>

      {/* Render all wells — شبکه ۴×۴ */}
      {wells.map((wellName, index) => {
        const wellData = wellsData[wellName]

        const row = Math.floor(index / 4)
        const col = index % 4
        const x = (col - 1.5) * spacing
        const z = (row - 1.5) * spacing

        if (!wellData) {
          return (
            <group key={wellName} position={[x, 0, z]}>
              <Text position={[0, 5, 0]} fontSize={0.5} color="#ffffff" anchorX="center" anchorY="middle">
                {wellName}
              </Text>
              <Text position={[0, 3.5, 0]} fontSize={0.35} color="#f87171" anchorX="center" anchorY="middle">
                Data unavailable
              </Text>
            </group>
          )
        }

        return (
          <group key={wellName} position={[x, 0, z]}>
            <Text
              position={[0, 5, 0]}
              fontSize={0.5}
              color="#ffffff"
              anchorX="center"
              anchorY="middle"
            >
              {wellName}
            </Text>
            <BOP bopData={wellData.bop} />
            <Wellbore
              depth={Math.min(wellData.totalDepth, 900)}
              data={wellData.depthData.slice(0, 14)}
              casings={wellData.casings}
            />
            <WellheadEquipment equipment={wellData.wellheadEquipment} wellName={wellName} />
          </group>
        )
      })}

      <Environment preset="sunset" />
    </>
  )
}

// Main 3D Scene - Single Well
function WellScene({ data, autoRotate = false }: { data: Well3DData; autoRotate?: boolean }) {
  const controlsRef = useRef<any>(null)

  // Calculate sensor positions at different depths
  const sensorPositions = data.depthData.map((segment, index) => {
    const depth = (index / data.depthData.length) * data.totalDepth
    const angle = (index / data.depthData.length) * Math.PI * 2
    const radius = 0.5
    return {
      position: [
        Math.cos(angle) * radius,
        -depth,
        Math.sin(angle) * radius
      ] as [number, number, number],
      depth,
      data: segment
    }
  })

  return (
    <>
      <PerspectiveCamera makeDefault position={[5, 2, 5]} fov={50} />
      <OrbitControls
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={3}
        maxDistance={20}
        autoRotate={autoRotate}
        autoRotateSpeed={0.6}
      />

      {/* Lighting */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <pointLight position={[-10, 10, -10]} intensity={0.5} />

      {/* Ground plane */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.1, 0]}>
        <planeGeometry args={[10, 10]} />
        <meshStandardMaterial color="#3a5f3a" />
      </mesh>

      {/* BOP - Blow Out Preventer */}
      <BOP bopData={data.bop} />

      {/* Wellbore with Casings */}
      <Wellbore depth={data.totalDepth} data={data.depthData} casings={data.casings} />

      {/* Depth labels */}
      <DepthLabels depth={data.totalDepth} segments={10} />

      {/* Sensor points */}
      {sensorPositions.map((sensor, index) => (
        <SensorPoint
          key={index}
          position={sensor.position}
          depth={sensor.depth}
          data={sensor.data}
          label={`Sensor ${index + 1}`}
        />
      ))}

      {/* Wellhead Equipment - تجهیزات سر چاهی */}
      <WellheadEquipment equipment={data.wellheadEquipment} wellName={data.wellName} />

      {/* Surface data display */}
      <Html position={[2, 2, 0]} distanceFactor={5}>
        <div className="surface-data-panel">
          <h3>{data.wellName} — داده‌های سطحی</h3>
          <div className="data-row">
            <span>فشار سرچاهی:</span>
            <span>{data.surfaceData.wellheadPressure.toFixed(2)} psi</span>
          </div>
          <div className="data-row">
            <span>دمای سرچاهی:</span>
            <span>{data.surfaceData.wellheadTemperature.toFixed(1)} °C</span>
          </div>
          <div className="data-row">
            <span>دبی / دبی‌سنج مجازی:</span>
            <span>{data.surfaceData.flowRate.toFixed(2)} bbl/day</span>
          </div>
        </div>
      </Html>

      {/* Environment */}
      <Environment preset="sunset" />
    </>
  )
}

export default function Well3D() {
  const [selectedWell, setSelectedWell] = useState<string>(DEHLORAN_WELLS[0].id)
  const [autoRotate, setAutoRotate] = useState(false)
  const [viewMode, setViewMode] = useState<'single' | 'multiple'>('single')
  const [chokePct, setChokePct] = useState(0)
  const [pumpSpeedPct, setPumpSpeedPct] = useState(0)
  const [whatIfResult, setWhatIfResult] = useState<any>(null)
  const [tick, setTick] = useState(Date.now())

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 10000)
    return () => window.clearInterval(id)
  }, [])

  const dehloranIds = useMemo(() => DEHLORAN_WELLS.map((w) => w.id), [])
  const liveWells = useMemo(() => getDehloranLiveState(tick), [tick])
  const liveSelected = liveWells.find((w) => w.id === selectedWell)

  const whatIfMutation = useMutation({
    mutationFn: (base: { flow_rate: number; pressure: number; temperature: number }) =>
      digitalTwinAPI.runWhatIfScenario({
        well_name: selectedWell,
        base_conditions: base,
        adjustments: { choke_pct: chokePct, pump_speed_pct: pumpSpeedPct },
        horizon_hours: 12,
      }),
    onSuccess: (data) => setWhatIfResult(data),
    onError: () => {
      // Local Dehloran what-if when twin API unavailable
      if (!displayDataRef.current) return
      const base = displayDataRef.current.surfaceData
      const flow =
        base.flowRate * (1 + chokePct / 100) * (1 + pumpSpeedPct / 80)
      const pressure = base.wellheadPressure * (1 - chokePct / 200) * (1 + pumpSpeedPct / 150)
      setWhatIfResult({
        projected: {
          flow_rate: Math.round(flow),
          pressure: Math.round(pressure),
          temperature: base.wellheadTemperature,
        },
        risk_level:
          flow > base.flowRate * 1.15 || pressure > base.wellheadPressure * 1.1
            ? 'elevated'
            : 'normal',
        source: 'local-dehloran-model',
      })
    },
  })

  const { data: wellsResponse } = useQuery({
    queryKey: ['wells-list-3d-dehloran'],
    queryFn: async () => {
      try {
        const response = await well3DAPI.getWells()
        const list = Array.isArray(response) ? response : response?.wells || []
        return list.length >= 8 ? list : dehloranIds
      } catch {
        return dehloranIds
      }
    },
    initialData: dehloranIds,
  })

  const wells: string[] = useMemo(() => {
    const list = Array.isArray(wellsResponse) ? wellsResponse : dehloranIds
    return list.length > 0 ? list : dehloranIds
  }, [wellsResponse, dehloranIds])

  useEffect(() => {
    if (wells.length > 0 && !wells.includes(selectedWell)) {
      setSelectedWell(wells[0])
    }
  }, [wells, selectedWell])

  const { data: apiWellData, isLoading } = useQuery({
    queryKey: ['well3d', selectedWell, tick],
    queryFn: () => well3DAPI.getWellData(selectedWell),
    refetchInterval: 15000,
    enabled: !!selectedWell,
    retry: 0,
  })

  const fallbackData = useMemo(
    () => buildDehloranWell3DData(selectedWell, tick) as Well3DData,
    [selectedWell, tick]
  )

  const displayData: Well3DData = useMemo(() => {
    if (apiWellData && apiWellData.depthData?.length) {
      return {
        ...fallbackData,
        ...apiWellData,
        wellName: apiWellData.wellName || selectedWell,
        surfaceData: apiWellData.surfaceData || fallbackData.surfaceData,
        depthData: apiWellData.depthData,
        bop: apiWellData.bop || fallbackData.bop,
        casings: apiWellData.casings?.length ? apiWellData.casings : fallbackData.casings,
        wellheadEquipment: apiWellData.wellheadEquipment || fallbackData.wellheadEquipment,
        riskZones: apiWellData.riskZones?.length ? apiWellData.riskZones : fallbackData.riskZones,
      }
    }
    return fallbackData
  }, [apiWellData, fallbackData, selectedWell])

  const displayDataRef = useRef(displayData)
  displayDataRef.current = displayData

  const { data: allWellsData } = useQuery({
    queryKey: ['wells3d-all-dehloran', wells, tick],
    queryFn: async () => {
      const local = buildAllDehloranWells3D(tick) as Record<string, Well3DData>
      const wellsData: Record<string, Well3DData | null> = { ...local }
      for (const wellName of wells.slice(0, 16)) {
        try {
          const remote = await well3DAPI.getWellData(wellName)
          if (remote?.depthData?.length) {
            wellsData[wellName] = { ...local[wellName], ...remote }
          }
        } catch {
          /* keep local Dehloran twin */
        }
      }
      return wellsData
    },
    enabled: viewMode === 'multiple',
    initialData: buildAllDehloranWells3D(tick) as Record<string, Well3DData>,
  })

  const wellLabel =
    DEHLORAN_WELLS.find((w) => w.id === selectedWell)?.nameFa || selectedWell

  return (
    <div className="well3d-container" dir="rtl">
      <div className="well3d-controls deh-3d-header">
        <div className="deh-3d-brand">
          <strong>{FIELD.nameFa}</strong>
          <span>{FIELD.clientFa} · نفت سنگین درجه سنگینی {FIELD.apiGravity}°</span>
        </div>
        <div className="control-group">
          <label>حالت نمایش:</label>
          <select
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value as 'single' | 'multiple')}
          >
            <option value="single">تک‌چاه</option>
            <option value="multiple">هر ۱۶ حلقه</option>
          </select>
        </div>
        {viewMode === 'single' && (
          <div className="control-group">
            <label>انتخاب چاه:</label>
            <select
              value={selectedWell}
              onChange={(e) => setSelectedWell(e.target.value)}
            >
              {wells.map((well) => {
                const fa = DEHLORAN_WELLS.find((w) => w.id === well)?.nameFa
                return (
                  <option key={well} value={well}>
                    {fa ? `${fa} (${well})` : well}
                  </option>
                )
              })}
            </select>
          </div>
        )}
        <div className="control-group">
          <label>
            <input
              type="checkbox"
              checked={autoRotate}
              onChange={(e) => setAutoRotate(e.target.checked)}
            />
            چرخش خودکار
          </label>
        </div>
        <div className="well-info">
          {viewMode === 'single' ? (
            <>
              <h2>
                {wellLabel}{' '}
                {liveSelected && (
                  <span
                    className="deh-3d-status"
                    style={{ color: STATUS_COLOR[liveSelected.status] }}
                  >
                    {STATUS_LABEL_FA[liveSelected.status]}
                  </span>
                )}
              </h2>
              <p>
                عمق کل: {displayData.totalDepth.toFixed(0)} m · فشار سرچاهی:{' '}
                {displayData.surfaceData.wellheadPressure} psi · دبی‌سنج مجازی:{' '}
                {displayData.surfaceData.flowRate} bbl/d
                {isLoading ? ' · به‌روزرسانی…' : ''}
              </p>
            </>
          ) : (
            <>
              <h2>نمای سه‌بعدی میدان دهلران</h2>
              <p>{FIELD.wellCount} حلقه چاه · دوقلوی دیجیتال</p>
            </>
          )}
        </div>
      </div>

      {viewMode === 'single' && liveSelected && (
        <div className="deh-3d-livebar">
          <span>فشار سرچاهی: <b>{liveSelected.thp} psi</b></span>
          <span>دما: <b>{liveSelected.tht} °C</b></span>
          <span>نفت: <b>{liveSelected.oilRate} bbl/d</b></span>
          <span>گاز: <b>{liveSelected.gasRate} Mscf/d</b></span>
          <span>آب: <b>{liveSelected.waterRate} bbl/d</b></span>
          <span>درصد آب تولیدی: <b>{liveSelected.waterCut}%</b></span>
          <span>پمپ: <b>{liveSelected.pumpOnline ? 'آنلاین' : 'آفلاین'}</b></span>
        </div>
      )}

      <div className="well3d-viewport">
        <Canvas className="well3d-canvas" shadows>
          <Suspense fallback={null}>
            {viewMode === 'single' ? (
              <WellScene data={displayData} autoRotate={autoRotate} />
            ) : (
              <MultipleWellsScene
                wellsData={allWellsData || (buildAllDehloranWells3D(tick) as Record<string, Well3DData>)}
                wells={wells.slice(0, 16)}
              />
            )}
          </Suspense>
        </Canvas>
      </div>

      <div className="well3d-legend">
        <div className="legend-section">
          <h3>وضعیت</h3>
          <div className="legend-item">
            <div className="legend-color normal"></div>
            <span>نرمال</span>
          </div>
          <div className="legend-item">
            <div className="legend-color warning"></div>
            <span>هشدار</span>
          </div>
          <div className="legend-item">
            <div className="legend-color critical"></div>
            <span>بحرانی</span>
          </div>
        </div>

        {displayData.bop && (
          <div className="legend-section">
            <h3>جلوگیری‌کننده از فوران</h3>
            <div className="legend-item">
              <div
                className="legend-color"
                style={{
                  background:
                    displayData.bop.status === 'open'
                      ? '#00ff00'
                      : displayData.bop.status === 'closed'
                        ? '#ff0000'
                        : '#ffaa00',
                }}
              ></div>
              <span>
                {displayData.bop.type} — {valveStatusFa(displayData.bop.status)}
              </span>
            </div>
            <div className="legend-item">
              <span style={{ fontSize: '12px', opacity: 0.8 }}>
                رتبه فشار: {displayData.bop.pressureRating.toLocaleString()} psi
              </span>
            </div>
          </div>
        )}

        {displayData.casings && displayData.casings.length > 0 && (
          <div className="legend-section">
            <h3>غلاف‌ها</h3>
            {displayData.casings.map((casing, index) => {
              const getCasingColor = () => {
                switch (casing.type) {
                  case 'conductor':
                    return '#8b4513'
                  case 'surface':
                    return '#4169e1'
                  case 'intermediate':
                    return '#32cd32'
                  case 'production':
                    return '#ff6347'
                  default:
                    return '#808080'
                }
              }
              return (
                <div key={index} className="legend-item">
                  <div className="legend-color" style={{ background: getCasingColor() }}></div>
                  <span>
                    {casingTypeFa(casing.type)}: {casing.outerDiameter}&quot; / {casing.innerDiameter}&quot; (۰–
                    {casing.depth}m)
                  </span>
                </div>
              )
            })}
          </div>
        )}

        {displayData.riskZones && displayData.riskZones.length > 0 && (
          <div className="legend-section">
            <h3>مناطق ریسک</h3>
            {displayData.riskZones.map((zone, idx) => (
              <div key={idx} className="legend-item">
                <div
                  className="legend-color"
                  style={{ background: zone.severity === 'critical' ? '#ff0000' : '#ffaa00' }}
                ></div>
                <span>
                  {zone.name}: {zone.fromDepth}m – {zone.toDepth}m
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {viewMode === 'single' && (
        <div className="well3d-whatif">
          <h3>تحلیل چه-اگر — دوقلوی دیجیتال دهلران</h3>
          <div className="whatif-controls">
            <label>
              تنظیم شیر کنترل جریان (%)
              <input
                type="range"
                min={-20}
                max={20}
                value={chokePct}
                onChange={(e) => setChokePct(Number(e.target.value))}
              />
              {chokePct}%
            </label>
            <label>
              سرعت پمپ (%)
              <input
                type="range"
                min={-20}
                max={20}
                value={pumpSpeedPct}
                onChange={(e) => setPumpSpeedPct(Number(e.target.value))}
              />
              {pumpSpeedPct}%
            </label>
            <button
              onClick={() =>
                whatIfMutation.mutate({
                  flow_rate: displayData.surfaceData.flowRate,
                  pressure: displayData.surfaceData.wellheadPressure,
                  temperature: displayData.surfaceData.wellheadTemperature,
                })
              }
              disabled={whatIfMutation.isPending}
            >
              {whatIfMutation.isPending ? 'در حال شبیه‌سازی…' : 'اجرای شبیه‌سازی'}
            </button>
          </div>
          {whatIfResult && (
            <div className="whatif-results">
              <p>
                <strong>دبی پیش‌بینی:</strong>{' '}
                {whatIfResult.projected?.flow_rate?.toFixed?.(1) ??
                  whatIfResult.projected_flow_rate ??
                  '—'}{' '}
                bbl/d
              </p>
              <p>
                <strong>فشار پیش‌بینی:</strong>{' '}
                {whatIfResult.projected?.pressure?.toFixed?.(1) ??
                  whatIfResult.projected_pressure ??
                  '—'}{' '}
                psi
              </p>
              <p>
                <strong>سطح ریسک:</strong>{' '}
                {riskLevelFa(String(whatIfResult.risk_level ?? whatIfResult.risk ?? '—'))}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


