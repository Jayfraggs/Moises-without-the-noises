const fs = require('fs');
const os = require('os');
const path = require('path');

const DEFAULT_MWNT_FOLDER = 'mwtn-outputs';

function resolveHomePath(filePath) {
  if (!filePath) return filePath;
  if (filePath === '~') return os.homedir();
  return filePath.replace(/^~(?=$|[\\/])/, os.homedir());
}

function getConfigFilePath(userDataPath) {
  return path.join(userDataPath || os.homedir(), 'mwtn-config.json');
}

function normalizeConfig(data = {}) {
  return {
    drivePath: data.drivePath ?? null,
    mwtnFolder: data.mwtnFolder || DEFAULT_MWNT_FOLDER,
  };
}

async function detectDrivePath() {
  const platform = process.platform;
  const homeDir = os.homedir();
  const candidates = [];

  if (platform === 'darwin') {
    const cloudStorageRoot = resolveHomePath('~/Library/CloudStorage');

    try {
      const cloudEntries = await fs.promises.readdir(cloudStorageRoot);
      const driveEntries = cloudEntries.filter((entry) =>
        entry.startsWith('GoogleDrive-')
      );

      for (const entry of driveEntries) {
        candidates.push(path.join(cloudStorageRoot, entry, 'My Drive'));
      }
    } catch (error) {
      // The CloudStorage directory is optional on macOS; continue to the
      // home-directory fallback below.
    }

    candidates.push(path.join(homeDir, 'Google Drive'));
  } else if (platform === 'win32') {
    const userProfile = process.env.USERPROFILE || homeDir;
    candidates.push(path.join(userProfile, 'Google Drive'));
    candidates.push(path.join(userProfile, 'My Drive'));
  } else {
    candidates.push(path.join(homeDir, 'Google Drive'));
    candidates.push(path.join(homeDir, 'google-drive'));
  }

  for (const candidate of candidates) {
    try {
      await fs.promises.access(candidate, fs.constants.F_OK);
      return { found: true, path: candidate, platform };
    } catch (error) {
      // Keep checking later candidates.
    }
  }

  return { found: false, path: null, platform };
}

function getDriveConfig(userDataPath) {
  const configPath = getConfigFilePath(userDataPath);

  try {
    const rawConfig = fs.readFileSync(configPath, 'utf8');
    const parsedConfig = JSON.parse(rawConfig);
    return normalizeConfig(parsedConfig);
  } catch (error) {
    if (error && error.code !== 'ENOENT') {
      console.warn('Failed to read Drive config:', error);
    }
    return {
      drivePath: null,
      mwtnFolder: DEFAULT_MWNT_FOLDER,
    };
  }
}

function setDriveConfig(userDataPath, drivePath, mwtnFolder) {
  const configPath = getConfigFilePath(userDataPath);
  const config = normalizeConfig({
    drivePath: drivePath || null,
    mwtnFolder: mwtnFolder,
  });

  try {
    fs.mkdirSync(path.dirname(configPath), { recursive: true });
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
    return config;
  } catch (error) {
    console.error('Failed to write Drive config:', error);
    throw error;
  }
}

module.exports = {
  DEFAULT_MWNT_FOLDER,
  detectDrivePath,
  getDriveConfig,
  setDriveConfig,
};
