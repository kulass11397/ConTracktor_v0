using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class ConTracktorLauncher
{
    [STAThread]
    private static void Main()
    {
        string executablePath = Process.GetCurrentProcess().MainModule.FileName;
        string appDirectory = Path.GetDirectoryName(executablePath);
        string runtimeDirectory = Path.GetFullPath(Path.Combine(appDirectory, "runtime"));
        string python = Path.Combine(runtimeDirectory, "python.exe");
        string script = Path.Combine(appDirectory, "app.py");
        string userRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ConTracktor_v1"
        );
        string requestedDatabase = Environment.GetEnvironmentVariable("CONTRACTOR_DB_PATH");
        string dataDirectory = String.IsNullOrWhiteSpace(requestedDatabase)
            ? Path.Combine(userRoot, "Data")
            : Path.GetDirectoryName(Path.GetFullPath(requestedDatabase));
        string logDirectory = String.IsNullOrWhiteSpace(requestedDatabase)
            ? Path.Combine(userRoot, "Logs")
            : Path.Combine(dataDirectory, "Logs");

        try
        {
            Directory.CreateDirectory(dataDirectory);
            Directory.CreateDirectory(logDirectory);
            File.WriteAllText(
                Path.Combine(logDirectory, "launcher-start.log"),
                "App=" + appDirectory + Environment.NewLine +
                "Runtime=" + runtimeDirectory + Environment.NewLine +
                "Python=" + python + Environment.NewLine +
                "Script=" + script + Environment.NewLine +
                "Smoke=" + Environment.GetEnvironmentVariable("CONTRACTOR_SMOKE_TEST") + Environment.NewLine +
                "Database=" + Environment.GetEnvironmentVariable("CONTRACTOR_DB_PATH"),
                Encoding.UTF8
            );
            string logPath = Path.Combine(
                logDirectory,
                "application_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log"
            );
            var output = new StringBuilder();
            var start = new ProcessStartInfo
            {
                FileName = python,
                Arguments = "\"" + script + "\"",
                WorkingDirectory = appDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                RedirectStandardOutput = false,
                RedirectStandardError = false
            };
            Environment.SetEnvironmentVariable("PYTHONHOME", runtimeDirectory);
            Environment.SetEnvironmentVariable("PYTHONPATH",
                Path.Combine(runtimeDirectory, "lib", "python3.12") + ";" +
                Path.Combine(runtimeDirectory, "lib", "python3.12", "lib-dynload"));
            Environment.SetEnvironmentVariable(
                "TCL_LIBRARY", Path.Combine(runtimeDirectory, "lib", "tcl8.6"));
            Environment.SetEnvironmentVariable(
                "TK_LIBRARY", Path.Combine(runtimeDirectory, "lib", "tk8.6"));
            if (String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("CONTRACTOR_DB_PATH")))
                Environment.SetEnvironmentVariable(
                    "CONTRACTOR_DB_PATH", Path.Combine(dataDirectory, "contractor_tracker.db"));

            using (Process process = new Process())
            {
                process.StartInfo = start;
                process.Start();
                File.AppendAllText(
                    Path.Combine(logDirectory, "launcher-start.log"),
                    Environment.NewLine + "Child PID=" + process.Id,
                    Encoding.UTF8
                );
                process.WaitForExit();
                if (output.Length > 0)
                    File.WriteAllText(logPath, output.ToString(), Encoding.UTF8);
                if (process.ExitCode != 0)
                    MessageBox.Show(
                        "ConTracktor closed because of an application error.\n\nDiagnostic log:\n" + logPath,
                        "ConTracktor_v1", MessageBoxButtons.OK, MessageBoxIcon.Error
                    );
            }
        }
        catch (Exception exception)
        {
            try
            {
                Directory.CreateDirectory(logDirectory);
                File.WriteAllText(
                    Path.Combine(logDirectory, "launcher-error.log"),
                    exception.ToString(), Encoding.UTF8
                );
            }
            catch { }
            MessageBox.Show(
                "ConTracktor could not start.\n\n" + exception.Message,
                "ConTracktor_v1", MessageBoxButtons.OK, MessageBoxIcon.Error
            );
        }
    }
}
