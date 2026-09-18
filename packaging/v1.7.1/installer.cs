using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

internal static class ConTracktorInstaller
{
    private const string ProductName = "ConTracktor_v1";
    private const string Version = "1.7.1";

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        string installDirectory = Environment.GetEnvironmentVariable("CONTRACTOR_INSTALL_TEST_DIR");
        if (String.IsNullOrWhiteSpace(installDirectory)) installDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs", ProductName
        );
        string dataDirectory = Environment.GetEnvironmentVariable("CONTRACTOR_INSTALL_TEST_DATA_DIR");
        if (String.IsNullOrWhiteSpace(dataDirectory)) dataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            ProductName, "Data"
        );
        bool unattendedTest = !String.IsNullOrWhiteSpace(
            Environment.GetEnvironmentVariable("CONTRACTOR_INSTALL_TEST_DIR"));

        try
        {
            if (!unattendedTest && Process.GetProcessesByName(ProductName).Length > 0)
            {
                MessageBox.Show(
                    "ConTracktor is currently open. Close it before installing this update so its SQLite database can be backed up safely.",
                    ProductName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (!unattendedTest && MessageBox.Show(
                "Install " + ProductName + " " + Version + " for this Windows user?\n\n" +
                "This update defaults Payroll to all employees across all sites, uses company-wide MONCON employee references, and combines each employee's weekly wages and cash-advance deductions into one row. Daily logs retain their work-project labels and project expenses remain separate. Former employee references are preserved.\n\n" +
                "Your active SQLite database will NOT be replaced. A timestamped safety copy will be made before application files are updated.\n\n" +
                "Application folder:\n" + installDirectory + "\n\n" +
                "Database backup folder:\n" + Path.Combine(dataDirectory, "Backups"),
                ProductName + " Setup", MessageBoxButtons.OKCancel, MessageBoxIcon.Information
            ) != DialogResult.OK) return;

            Directory.CreateDirectory(installDirectory);
            Directory.CreateDirectory(dataDirectory);
            CreateSafetyBackups(installDirectory, dataDirectory);
            ExtractPayload(installDirectory);
            File.WriteAllText(
                Path.Combine(dataDirectory, "LAST_INSTALLED_UPDATE.txt"),
                "Version=" + Version + Environment.NewLine +
                "Installed=" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + Environment.NewLine +
                "DatabasePreserved=True" + Environment.NewLine,
                Encoding.UTF8
            );

            string executable = Path.Combine(installDirectory, ProductName + ".exe");
            if (!unattendedTest)
            {
                CreateShortcut(Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    ProductName + ".lnk"), executable);
                string startMenu = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
                    "Programs", ProductName);
                Directory.CreateDirectory(startMenu);
                CreateShortcut(Path.Combine(startMenu, ProductName + ".lnk"), executable);
                WriteUninstallRegistration(installDirectory, executable);
                MessageBox.Show(
                    ProductName + " " + Version + " was installed successfully.\n\n" +
                    "Your existing records were retained. A separate database backup is created before employee references are renamed to MONCON on first launch.",
                    ProductName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
                Process.Start(executable);
            }
        }
        catch (IOException exception)
        {
            MessageBox.Show(
                "Installation could not replace a file. Close ConTracktor and run this installer again.\n\n" + exception.Message,
                ProductName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        catch (Exception exception)
        {
            MessageBox.Show("Installation failed. No database replacement was performed.\n\n" + exception.Message,
                ProductName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void ExtractPayload(string installDirectory)
    {
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        {
            if (resource == null) throw new InvalidOperationException("Installer payload is missing.");
            using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
            {
                string root = Path.GetFullPath(installDirectory).TrimEnd(
                    Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string destination = Path.GetFullPath(Path.Combine(root, entry.FullName));
                    if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Unsafe installer entry was rejected.");
                    if (String.IsNullOrEmpty(entry.Name))
                    {
                        Directory.CreateDirectory(destination);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    entry.ExtractToFile(destination, true);
                }
            }
        }
    }

    private static void CreateSafetyBackups(string installDirectory, string dataDirectory)
    {
        string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string userRoot = Directory.GetParent(dataDirectory).FullName;

        if (Directory.Exists(installDirectory) && Directory.GetFileSystemEntries(installDirectory).Length > 0)
        {
            string appBackup = Path.Combine(userRoot, "AppBackups", "Before_v" + Version + "_" + stamp);
            CopyDirectory(installDirectory, appBackup);
        }

        string database = Path.Combine(dataDirectory, "contractor_tracker.db");
        if (File.Exists(database))
        {
            string dataBackup = Path.Combine(dataDirectory, "Backups", "Before_v" + Version + "_" + stamp);
            Directory.CreateDirectory(dataBackup);
            foreach (string suffix in new string[] { "", "-wal", "-shm" })
            {
                string source = database + suffix;
                if (File.Exists(source))
                    File.Copy(source, Path.Combine(dataBackup, Path.GetFileName(source)), true);
            }
        }
    }

    private static void CopyDirectory(string sourceDirectory, string destinationDirectory)
    {
        Directory.CreateDirectory(destinationDirectory);
        foreach (string directory in Directory.GetDirectories(sourceDirectory, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(directory.Replace(sourceDirectory, destinationDirectory));
        foreach (string file in Directory.GetFiles(sourceDirectory, "*", SearchOption.AllDirectories))
        {
            string destination = file.Replace(sourceDirectory, destinationDirectory);
            Directory.CreateDirectory(Path.GetDirectoryName(destination));
            File.Copy(file, destination, true);
        }
    }

    private static void CreateShortcut(string shortcutPath, string target)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(shellType);
        dynamic shortcut = shell.CreateShortcut(shortcutPath);
        shortcut.TargetPath = target;
        shortcut.WorkingDirectory = Path.GetDirectoryName(target);
        shortcut.IconLocation = target + ",0";
        shortcut.Description = ProductName;
        shortcut.Save();
    }

    private static void WriteUninstallRegistration(string installDirectory, string executable)
    {
        using (var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + ProductName))
        {
            key.SetValue("DisplayName", ProductName);
            key.SetValue("DisplayVersion", Version);
            key.SetValue("Publisher", "ConTracktor");
            key.SetValue("DisplayIcon", executable);
            key.SetValue("InstallLocation", installDirectory);
            key.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
        }
    }
}
