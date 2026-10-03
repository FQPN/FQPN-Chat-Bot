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

## How installed apps get the update
Nothing extra to do: publishing the release is enough.
- The app asks GitHub for the newest release (the repository must be **public**), compares it with its own version number, and downloads the file named `FQPN-Chat-Bot-Setup-<version>.exe` from that release.
- The build stamps the number from your tag (`v1.2.3` becomes `1.2.3`) into the app, so always create the tag with the `v` and three numbers.
- The update is installed silently over the old one; the commands, timers and Twitch login live in `%APPDATA%\TwitchChatBot` and are never touched.
- Versions installed **before** this feature existed cannot update themselves: people install the first updating version by hand once, and from then on it is automatic.
- Windows' Smart App Control also blocks an unsigned update, just as it blocks the unsigned first install. Signing the installer fixes both.
