import fs from "fs";
import path from "path";

// Safe .env loader (removes external dependency on 'dotenv' package)
function loadEnv() {
  const envPath = path.join(process.cwd(), ".env");
  if (fs.existsSync(envPath)) {
    try {
      const lines = fs.readFileSync(envPath, "utf-8").split(/\r?\n/);
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const match = trimmed.match(/^\s*([^#=]+)\s*=\s*(.*)$/);
        if (match) {
          const key = match[1].trim();
          let value = match[2].trim();
          // Remove surrounding quotes if any
          if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.substring(1, value.length - 1);
          }
          value = value.replace(/\\n/g, "\n");
          // Only set if not already set by system environment
          if (process.env[key] === undefined) {
            process.env[key] = value;
          }
        }
      }
    } catch (err) {
      console.warn("Warning: Failed to load .env file locally:", err.message);
    }
  }
}

loadEnv();

const BASE_URL = process.env.METABASE_BASE_URL || "https://metabase.workincentives.me";
const USERNAME = process.env.METABASE_USERNAME;
const PASSWORD = process.env.METABASE_PASSWORD;
const SESSION_FILE = path.join(process.cwd(), ".metabase_session");

// Helper to load session token or authenticate if expired
async function getSessionToken() {
  if (process.env.METABASE_SESSION_TOKEN) {
    return process.env.METABASE_SESSION_TOKEN.trim();
  }

  if (fs.existsSync(SESSION_FILE)) {
    const stats = fs.statSync(SESSION_FILE);
    // Token is valid for 14 days in Metabase by default, let's assume 7 days to be safe
    const ageInHours = (Date.now() - stats.mtimeMs) / (1000 * 60 * 60);
    if (ageInHours < 24 * 7) {
      return fs.readFileSync(SESSION_FILE, "utf-8").trim();
    }
  }

  if (!USERNAME || !PASSWORD) {
    throw new Error(
      "Missing METABASE_USERNAME or METABASE_PASSWORD or METABASE_SESSION_TOKEN in your .env file.\n" +
      "Please configure these to your .env file:\n" +
      "METABASE_BASE_URL=https://metabase.workincentives.me\n" +
      "METABASE_SESSION_TOKEN=your-session-cookie-value-for-google-oauth"
    );
  }

  console.log("Authenticating with Metabase...");
  const res = await fetch(`${BASE_URL}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Authentication failed (${res.status}): ${errText}`);
  }

  const data = await res.json();
  const token = data.id;
  fs.writeFileSync(SESSION_FILE, token, "utf-8");
  return token;
}

// Universal fetch wrapper
async function metabaseFetch(endpoint, options = {}) {
  const token = await getSessionToken();
  const url = `${BASE_URL}${endpoint}`;
  
  const headers = {
    "Content-Type": "application/json",
    "X-Metabase-Session": token,
    ...(options.headers || {}),
  };

  const response = await fetch(url, { ...options, headers });
  
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Metabase API Error on ${endpoint} (${response.status}): ${errText}`);
  }

  return response.json();
}

async function testConnection() {
  try {
    const token = await getSessionToken();
    console.log("✓ Successfully authenticated with Metabase!");
    const user = await metabaseFetch("/api/user/current");
    console.log(`✓ Connected as: ${user.common_name} (${user.email})`);
  } catch (error) {
    console.error("✗ Connection failed:", error.message);
  }
}

async function getDashboard(id) {
  try {
    console.log(`Fetching Dashboard ${id}...`);
    const dash = await metabaseFetch(`/api/dashboard/${id}`);
    
    console.log(`\n========================================`);
    console.log(`Dashboard: ${dash.name}`);
    console.log(`Description: ${dash.description || "No description"}`);
    console.log(`========================================\n`);

    // Write to scratch file for inspection
    const outPath = path.join(process.cwd(), "scratch", `dashboard_${id}.json`);
    if (!fs.existsSync(path.dirname(outPath))) {
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
    }
    fs.writeFileSync(outPath, JSON.stringify(dash, null, 2), "utf-8");
    console.log(`[Debug] Full dashboard JSON saved to ${outPath}`);

    // List Tabs
    if (dash.tabs && dash.tabs.length > 0) {
      console.log("Tabs:");
      dash.tabs.forEach(t => console.log(`  - [ID: ${t.id}] ${t.name}`));
      console.log("");
    }

    // Metabase dashboard API returned cards can be in ordered_cards or dashcards or cards
    const cards = dash.ordered_cards || dash.dashcards || dash.cards;
    if (!cards) {
      console.log("No cards found in this dashboard. Keys in response:", Object.keys(dash));
      return;
    }

    console.log("Cards / Questions in this Dashboard:");
    cards.forEach((oc, idx) => {
      const card = oc.card;
      // Filter mapping
      const tabInfo = oc.dashboard_tab_id ? `(Tab ID: ${oc.dashboard_tab_id})` : "";
      console.log(`${idx + 1}. [Card ID: ${card.id}] [Dashcard ID: ${oc.id}] ${card.name} ${tabInfo}`);
      if (card.description) console.log(`   Description: ${card.description}`);
      console.log(`   Type: ${card.dataset_query?.type || "unknown"}`);
      
      // Print parameter mappings if any
      if (oc.parameter_mappings && oc.parameter_mappings.length > 0) {
        console.log(`   Parameter Mappings:`);
        oc.parameter_mappings.forEach(pm => {
          console.log(`     - Parameter "${pm.parameter_id}" -> Target: ${JSON.stringify(pm.target)}`);
        });
      }
      console.log("----------------------------------------");
    });
  } catch (error) {
    console.error("✗ Error fetching dashboard:", error.message);
  }
}

function parseParameters(paramsStr) {
  if (!paramsStr || paramsStr === "[]") return [];
  
  // Try direct JSON parse
  try {
    return JSON.parse(paramsStr);
  } catch (e) {
    // If it's single quotes or PowerShell stripped quotes, let's fix common formats
    try {
      let fixed = paramsStr.replace(/'/g, '"');
      return JSON.parse(fixed);
    } catch (e2) {
      // Try parsing key=value format (e.g. "d9a6252e=Last 30 Days")
      const match = paramsStr.match(/^([^=]+)=(.*)$/);
      if (match) {
        const id = match[1].trim();
        let val = match[2].trim();
        // Remove surrounding quotes if any
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.substring(1, val.length - 1);
        }
        return [{
          id: id,
          type: "string/=", // Default Metabase parameter type
          value: [val]
        }];
      }
    }
  }
  console.log("Warning: Failed to parse parameters as JSON or key=value format. Running without parameters.");
  return [];
}

async function queryCard(cardId, paramsStr = "[]") {
  try {
    const params = parseParameters(paramsStr);

    console.log(`Querying Card ${cardId}...`);
    const results = await metabaseFetch(`/api/card/${cardId}/query`, {
      method: "POST",
      body: JSON.stringify({ parameters: params }),
    });

    displayResults(results);
  } catch (error) {
    console.error("✗ Error querying card:", error.message);
  }
}

async function queryDashcard(dashboardId, dashcardId, cardId, paramsStr = "[]") {
  try {
    const params = parseParameters(paramsStr);

    console.log(`Querying Dashcard ${dashcardId} (Card ${cardId}) on Dashboard ${dashboardId}...`);
    
    const results = await metabaseFetch(`/api/dashboard/${dashboardId}/dashcard/${dashcardId}/card/${cardId}/query`, {
      method: "POST",
      body: JSON.stringify({ parameters: params }),
    });

    displayResults(results);
  } catch (error) {
    console.error("✗ Error querying dashcard:", error.message);
  }
}

async function listDatabases() {
  try {
    console.log("Fetching databases available in Metabase...");
    const databases = await metabaseFetch("/api/database");
    console.log("\nAvailable Databases:");
    databases.data.forEach(db => {
      console.log(`- [ID: ${db.id}] ${db.name} (Engine: ${db.engine})`);
    });
  } catch (error) {
    console.error("✗ Error listing databases:", error.message);
  }
}

async function runSql(databaseId, sqlQuery) {
  try {
    console.log(`Running custom SQL query on Database ID ${databaseId}...`);
    const results = await metabaseFetch("/api/dataset", {
      method: "POST",
      body: JSON.stringify({
        database: parseInt(databaseId, 10),
        type: "native",
        native: {
          query: sqlQuery,
          "template-tags": {}
        }
      }),
    });

    displayResults(results);
  } catch (error) {
    console.error("✗ Error running SQL query:", error.message);
  }
}

function displayResults(results) {
  const data = results.data;
  if (!data || !data.rows) {
    console.log("No data returned or invalid format.");
    console.log(JSON.stringify(results, null, 2));
    return;
  }

  const columns = data.cols.map(c => c.display_name || c.name);
  const rows = data.rows;

  console.log(`\nReturned ${rows.length} rows, ${columns.length} columns.`);
  
  const previewRows = rows.slice(0, 30);
  
  const tableData = previewRows.map(row => {
    const rowObj = {};
    columns.forEach((col, idx) => {
      rowObj[col] = row[idx];
    });
    return rowObj;
  });

  console.table(tableData);

  if (rows.length > 30) {
    console.log(`... and ${rows.length - 30} more rows.`);
  }

  const outputPath = path.join(process.cwd(), "scratch", "metabase_results.json");
  if (!fs.existsSync(path.dirname(outputPath))) {
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  }
  
  const fullJson = rows.map(row => {
    const rowObj = {};
    data.cols.forEach((col, idx) => {
      rowObj[col.name] = row[idx];
    });
    return rowObj;
  });

  fs.writeFileSync(outputPath, JSON.stringify(fullJson, null, 2), "utf-8");
  console.log(`\n✓ Full result dataset written to: ${outputPath}`);
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  if (!command) {
    console.log(`
Metabase CLI Integrator
=======================
Usage:
  node scripts/metabase.js login                                                            - Test connection and log in
  node scripts/metabase.js dashboard <id>                                                   - List cards & tabs in a dashboard
  node scripts/metabase.js query-card <card_id> '[params_json]'                              - Query a card's data
  node scripts/metabase.js query-dashcard <dash_id> <dashcard_id> <card_id> '[params_json]' - Query a card in dashboard context
  node scripts/metabase.js databases                                                        - List database connections in Metabase
  node scripts/metabase.js sql <db_id> "<query>"                                            - Run direct SQL query
    `);
    process.exit(0);
  }

  switch (command) {
    case "login":
      await testConnection();
      break;
    case "dashboard":
      if (!args[1]) {
        console.error("Please specify a Dashboard ID (e.g. 27)");
        process.exit(1);
      }
      await getDashboard(args[1]);
      break;
    case "query-card":
      if (!args[1]) {
        console.error("Please specify a Card ID");
        process.exit(1);
      }
      await queryCard(args[1], args[2]);
      break;
    case "query-dashcard":
      if (!args[1] || !args[2] || !args[3]) {
        console.error("Usage: query-dashcard <dashboard_id> <dashcard_id> <card_id> [params_json]");
        process.exit(1);
      }
      await queryDashcard(args[1], args[2], args[3], args[4]);
      break;
    case "databases":
      await listDatabases();
      break;
    case "sql":
      if (!args[1] || !args[2]) {
        console.error("Usage: sql <database_id> \"<query>\"");
        process.exit(1);
      }
      await runSql(args[1], args[2]);
      break;
    default:
      console.error(`Unknown command: ${command}`);
      process.exit(1);
  }
}

main().catch(err => {
  console.error("Fatal Error:", err.message);
  process.exit(1);
});
