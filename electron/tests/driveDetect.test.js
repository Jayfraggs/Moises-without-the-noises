const fs = require('fs');
const os = require('os');
const path = require('path');

const { detectDrivePath, getDriveConfig, setDriveConfig } = require('../driveDetect');

describe('driveDetect', () => {
  let originalPlatform;
  let originalUserProfile;
  let tempRoot;

  beforeEach(() => {
    originalPlatform = process.platform;
    originalUserProfile = process.env.USERPROFILE;
    tempRoot = path.join(os.tmpdir(), `mwtn-drive-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    fs.mkdirSync(tempRoot, { recursive: true });
  });

  afterEach(() => {
    jest.restoreAllMocks();

    if (process.env.USERPROFILE !== originalUserProfile) {
      if (originalUserProfile === undefined) {
        delete process.env.USERPROFILE;
      } else {
        process.env.USERPROFILE = originalUserProfile;
      }
    }

    Object.defineProperty(process, 'platform', {
      value: originalPlatform,
      configurable: true,
    });

    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  function setPlatform(platform) {
    Object.defineProperty(process, 'platform', {
      value: platform,
      configurable: true,
    });
  }

  test('T1 macOS CloudStorage entry exists', async () => {
    setPlatform('darwin');

    const expectedPath = path.join(
      os.homedir(),
      'Library',
      'CloudStorage',
      'GoogleDrive-user@gmail.com',
      'My Drive'
    );

    jest.spyOn(fs.promises, 'readdir').mockResolvedValue([
      'GoogleDrive-user@gmail.com',
      'OtherFolder',
    ]);

    jest.spyOn(fs.promises, 'access').mockImplementation(async (target) => {
      if (target === expectedPath) {
        return undefined;
      }
      throw new Error('ENOENT');
    });

    const result = await detectDrivePath();

    expect(result).toEqual({
      found: true,
      path: expectedPath,
      platform: 'darwin',
    });
  });

  test('T2 macOS no CloudStorage entries', async () => {
    setPlatform('darwin');

    jest.spyOn(fs.promises, 'readdir').mockResolvedValue([]);
    jest.spyOn(fs.promises, 'access').mockRejectedValue(new Error('ENOENT'));

    const result = await detectDrivePath();

    expect(result).toEqual({
      found: false,
      path: null,
      platform: 'darwin',
    });
  });

  test('T3 Windows Google Drive folder exists', async () => {
    setPlatform('win32');
    process.env.USERPROFILE = tempRoot;

    const expectedPath = path.join(tempRoot, 'Google Drive');

    jest.spyOn(fs.promises, 'access').mockImplementation(async (target) => {
      if (target === expectedPath) {
        return undefined;
      }
      throw new Error('ENOENT');
    });

    const result = await detectDrivePath();

    expect(result).toEqual({
      found: true,
      path: expectedPath,
      platform: 'win32',
    });
  });

  test('T4 no candidates on any platform', async () => {
    setPlatform('linux');
    jest.spyOn(fs.promises, 'access').mockRejectedValue(new Error('ENOENT'));

    const result = await detectDrivePath();

    expect(result.found).toBe(false);
    expect(result.path).toBeNull();
    expect(result.platform).toBe('linux');
  });

  test('T5 setDriveConfig + getDriveConfig roundtrip', () => {
    const drivePath = path.join(tempRoot, 'Google Drive');
    const mwtnFolder = 'custom-output-folder';

    setDriveConfig(tempRoot, drivePath, mwtnFolder);
    const config = getDriveConfig(tempRoot);

    expect(config).toEqual({
      drivePath,
      mwtnFolder,
    });
  });

  test('T6 config file missing returns default config', () => {
    const config = getDriveConfig(path.join(tempRoot, 'missing-user-data'));

    expect(config).toEqual({
      drivePath: null,
      mwtnFolder: 'mwtn-outputs',
    });
  });
});
