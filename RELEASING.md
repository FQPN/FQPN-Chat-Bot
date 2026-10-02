# Publishing a new version

You never build the installer by hand. GitHub builds it for you on a Windows machine.

1. Add a few lines about what changed to the top of `CHANGELOG.md`.
2. Commit and push as usual.
3. Create the version tag (use the next number, for example `v1.0.1`):
   ```
   git tag v1.0.1
   git push origin v1.0.1
   ```
4. Open the **Actions** tab of your repository. A run called **Build installer** starts. It takes about 5 minutes.
5. When it turns green, open **Releases**: the new `FQPN-Chat-Bot-Setup-1.0.1.exe` is there for everyone to download.

To try a build without publishing a version, open **Actions → Build installer → Run workflow**.
The installer is then attached to that run (look for **installer** at the bottom of the run page).

If the run turns red, open it, click the red step, and copy the last lines of its log.

**Testing before you share:** install the Setup.exe on a PC that does not have Python, or in Windows Sandbox, and check that the dashboard opens and Twitch connects.
