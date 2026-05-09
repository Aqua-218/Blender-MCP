import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'node:fs';
import path from 'node:path';

const repoRoot = '/root/Programming/Blender-MCP';
const sourceBlend = path.join(
  repoRoot,
  'workspace',
  'mcp-fushimi-honden-20260428-035503-658697',
  'projects',
  'fushimi-inari-honden',
  'fushimi-inari-honden-20260428-035503-658697.blend'
);
const runStamp = new Date().toISOString().replace(/[:.]/g, '-');
const outputRoot = path.join(repoRoot, 'workspace', `mcp-node-repair-${runStamp}`);
fs.mkdirSync(outputRoot, { recursive: true });

function loadEnvFile(filePath) {
  const env = {};
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
      continue;
    }
    const [key, ...rest] = trimmed.split('=');
    env[key] = rest.join('=');
  }
  return env;
}

const env = {
  ...process.env,
  ...loadEnvFile(path.join(repoRoot, '.env')),
  BLENDER_MCP_TRANSPORT: 'stdio',
  BLENDER_MCP_WORKSPACE_ROOTS: path.join(repoRoot, 'workspace'),
  BLENDER_MCP_CONTROLLER_PORT: String(9300 + Math.floor(Math.random() * 300)),
};

const client = new Client({ name: 'mcp-node-honden-repair', version: '1.0.0' }, { capabilities: {} });
const transport = new StdioClientTransport({
  command: path.join(repoRoot, '.venv', 'bin', 'python'),
  args: ['-m', 'mcp_server.main', '--transport', 'stdio'],
  env,
  cwd: repoRoot,
  stderr: 'pipe',
});

if (transport.stderr) {
  transport.stderr.on('data', chunk => process.stderr.write(chunk));
}

let requestCounter = 1;
function nextRequestId(label) {
  requestCounter += 1;
  return `node-repair-${label}-${runStamp}-${requestCounter}`;
}

async function callTool(name, args) {
  const result = await client.callTool({ name, arguments: args });
  if (result.status === 'failed') {
    throw new Error(`${name} failed: ${JSON.stringify(result.errors ?? result)}`);
  }
  return result;
}

async function findByNames(projectId, names) {
  const result = await callTool('find_objects', {
    request_id: nextRequestId('find'),
    project_id: projectId,
    names,
  });
  return result.objects ?? [];
}

async function findOne(projectId, name) {
  const objects = await findByNames(projectId, [name]);
  const object = objects.find(candidate => candidate.name === name);
  if (!object) {
    throw new Error(`Object not found: ${name}`);
  }
  return object;
}

async function transformByName(projectId, name, payload) {
  const object = await findOne(projectId, name);
  return callTool('transform_object', {
    request_id: nextRequestId(`transform-${name}`),
    project_id: projectId,
    target_id: object.object_id,
    ...payload,
  });
}

async function setVisibilityByNames(projectId, names, visible) {
  return callTool('set_object_visibility', {
    request_id: nextRequestId('visibility'),
    project_id: projectId,
    names,
    visible,
  });
}

async function setLightByName(projectId, name, payload) {
  const object = await findOne(projectId, name);
  return callTool('set_light', {
    request_id: nextRequestId(`light-${name}`),
    project_id: projectId,
    light_id: object.object_id,
    ...payload,
  });
}

async function createCube(projectId, name, location, dimensions) {
  const scale = dimensions.map(value => value * 0.5);
  const result = await callTool('create_primitive', {
    request_id: nextRequestId(`cube-${name}`),
    project_id: projectId,
    primitive_type: 'cube',
    name,
    location,
    scale,
  });
  return result.created_object_ids?.[0];
}

async function createMaterial(projectId, name, payload) {
  const result = await callTool('create_pbr_material', {
    request_id: nextRequestId(`material-${name}`),
    project_id: projectId,
    name,
    ...payload,
  });
  return result.material?.material_id;
}

async function applyMaterial(projectId, materialId, targetIds) {
  return callTool('apply_material', {
    request_id: nextRequestId('apply-material'),
    project_id: projectId,
    material_id: materialId,
    target_ids: targetIds,
  });
}

try {
  await client.connect(transport);

  const opened = await callTool('open_project', {
    request_id: nextRequestId('open'),
    blend_file_path: sourceBlend,
  });
  const projectId = opened.project_id;

  await callTool('create_snapshot', {
    request_id: nextRequestId('snapshot'),
    project_id: projectId,
    reason: 'pre_destructive_change',
  });

  await transformByName(projectId, 'GableUpright', {
    location: [0.0, 2.58, 5.72],
    scale: [0.18, 0.08, 1.72],
  });
  await transformByName(projectId, 'GableCrossbarA', {
    location: [0.0, 2.58, 5.42],
    scale: [4.8, 0.08, 0.14],
  });
  await transformByName(projectId, 'GableCrossbarB', {
    location: [0.0, 2.58, 6.02],
    scale: [2.8, 0.08, 0.12],
  });
  await transformByName(projectId, 'GableUprightAccent', {
    location: [0.0, 2.58, 5.72],
    scale: [0.2, 0.1, 1.72],
  });
  await transformByName(projectId, 'GableCrossbarAAccent', {
    location: [0.0, 2.58, 5.42],
    scale: [4.8, 0.1, 0.14],
  });
  await transformByName(projectId, 'GableCrossbarBAccent', {
    location: [0.0, 2.58, 6.02],
    scale: [2.8, 0.1, 0.12],
  });

  await setVisibilityByNames(projectId, ['Katsuogi1', 'Katsuogi2', 'Katsuogi3', 'Katsuogi4', 'Katsuogi5'], false).catch(() => {});
  await setVisibilityByNames(projectId, ['LeftServiceRoof', 'LeftServiceHouse'], false).catch(() => {});
  await setLightByName(projectId, 'ShrineDayKey', { intensity: 1200.0, size: 10.0 }).catch(() => {});
  await setLightByName(projectId, 'FacadeLift', { intensity: 1100.0, size: 10.0 }).catch(() => {});
  await setLightByName(projectId, 'RoofEdgeRim', { intensity: 180.0, size: 7.0 }).catch(() => {});

  const courtOverlayId = await createCube(projectId, 'NodeRepairCourtOverlay', [0.0, -3.0, 0.03], [18.0, 14.5, 0.06]).catch(() => null);
  if (courtOverlayId) {
    const courtMaterialId = await createMaterial(projectId, 'NodeRepairPackedEarth', {
      base_color: [0.48, 0.44, 0.38, 1.0],
      roughness: 0.96,
      metallic: 0.0,
    }).catch(() => null);
    if (courtMaterialId) {
      await applyMaterial(projectId, courtMaterialId, [courtOverlayId]).catch(() => {});
    }
  }

  await setVisibilityByNames(projectId, ['HondenReferenceCam', 'HondenSlightRightCam', 'HondenWideCam'], false).catch(() => {});

  await callTool('set_render_settings', {
    request_id: nextRequestId('render-settings'),
    project_id: projectId,
    preset_name: 'final',
  });

  const cameraSpecs = [
    {
      label: 'reference',
      name: 'NodeRepairReferenceCam',
      location: [0.0, -17.4, 6.8],
      rotation: [1.08, 0.0, 0.0],
      focal_length: 44.0,
    },
    {
      label: 'slight-right',
      name: 'NodeRepairSlightRightCam',
      location: [2.4, -17.0, 6.7],
      rotation: [1.08, 0.0, 0.12],
      focal_length: 44.0,
    },
    {
      label: 'wide',
      name: 'NodeRepairWideCam',
      location: [0.0, -20.2, 7.8],
      rotation: [1.02, 0.0, 0.0],
      focal_length: 40.0,
    },
  ];

  const renders = [];
  for (const spec of cameraSpecs) {
    const created = await callTool('create_camera', {
      request_id: nextRequestId(`camera-${spec.label}`),
      project_id: projectId,
      name: spec.name,
    });
    const cameraId = created.camera.camera_id;
    await callTool('set_camera', {
      request_id: nextRequestId(`camera-set-${spec.label}`),
      project_id: projectId,
      camera_id: cameraId,
      location: spec.location,
      rotation: spec.rotation,
      focal_length: spec.focal_length,
    });
    const render = await callTool('render_preview', {
      request_id: nextRequestId(`render-${spec.label}`),
      project_id: projectId,
      camera_id: cameraId,
      output_path: `renders/node-repair-${spec.label}-${runStamp}.png`,
    });
    renders.push({ label: spec.label, renderPath: render.image_paths?.[0] ?? render.image_path, cameraId });
  }

  const savePath = path.join(outputRoot, 'projects', `fushimi-inari-honden-node-repair-${runStamp}.blend`);
  const saved = await callTool('save_project_as', {
    request_id: nextRequestId('save-as'),
    project_id: projectId,
    output_path: savePath,
    overwrite: true,
    destructive_confirmation: true,
  });

  console.log(JSON.stringify({
    sourceBlend,
    projectId,
    outputBlend: saved.blend_file_path,
    renders,
  }, null, 2));
} finally {
  await transport.close().catch(() => {});
  await client.close().catch(() => {});
}