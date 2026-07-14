const url = 'https://stitch.googleapis.com/mcp';
const apiKey = 'AQ.Ab8RN6LkUGoYBga-e0R7PNxJNe6ClIKn5wii6R5dZDQCsOryVA';

async function callTool(toolName, params = {}) {
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'X-Goog-Api-Key': apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: Math.floor(Math.random() * 1000000),
        method: `tools/call`,
        params: {
          name: toolName,
          arguments: params
        }
      })
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    const json = await res.json();
    if (json.error) {
      throw new Error(`JSON-RPC error: ${JSON.stringify(json.error)}`);
    }

    return json.result;
  } catch (error) {
    console.error(`Error calling tool ${toolName}:`, error);
    throw error;
  }
}

module.exports = {
  callTool,
  createProject: (title) => callTool('create_project', { title }),
  getProject: (name) => callTool('get_project', { name }),
  listProjects: (filter) => callTool('list_projects', { filter }),
  listScreens: (projectId) => callTool('list_screens', { projectId }),
  getScreen: (name, projectId, screenId) => callTool('get_screen', { name, projectId, screenId }),
  generateScreenFromText: (projectId, prompt, options = {}) => callTool('generate_screen_from_text', { projectId, prompt, ...options }),
  editScreens: (projectId, prompt, screenNames, options = {}) => callTool('edit_screens', { projectId, prompt, screenNames, ...options }),
  generateVariants: (projectId, prompt, screenName, options = {}) => callTool('generate_variants', { projectId, prompt, screenName, ...options }),
  createDesignSystem: (projectId, name, theme, options = {}) => callTool('create_design_system', { projectId, name, theme, ...options }),
  listDesignSystems: (projectId) => callTool('list_design_systems', { projectId }),
  applyDesignSystem: (projectId, designSystem, screenNames) => callTool('apply_design_system', { projectId, designSystem, screenNames })
};
