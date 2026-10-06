# Git history of Sentinela (bootstrap)

Copied by `omoikane/bin/bootstrap.py`: the commits of `Sentinela` without merges, newest first, at most 300, as date, commit and subject, then the body. A body often holds the reason for a change.

## 2026-10-06 5289cfc fix(chat): dedupe digest reposts, copy text, permission banner and version

Bundled notifications re-list history on every update, which rendered one message several times. Save textLines line-by-line and dedupe same-text reposts inside a 10s window per conversation instead of dropping every repeat forever. Also make links tappable, copy message text on long-press, re-request media permission from a chat-list banner, and show the app version in the list footer.

## 2026-10-06 ed4740f fix: delete chats from home screen and show recovered media

Long-press a conversation to delete its messages and media copies, or
delete and ignore the contact. A new per-contact "Mensagens" switch
(schema v6) stops saving text from ignored contacts; contacts with
settings stay on the allowlist even after their history is gone.

Deleted media was never shown on pt-BR phones: the deletion notice was
matched only in English, and media was linked to the message only at
detection time, within a 5 min in-memory window. Media copies are now
linked to the sender's latest message as soon as the file appears, a
MediaStore observer complements FileObserver (unreliable under FUSE on
Android 11+), Sent folders are skipped, and copies of deleted messages
are exempt from cleanup. Thumbnails and a video/audio action open the
file through a FileProvider. pt-BR unread-summary titles are no longer
saved as contacts.

Add a workflow that tests and builds the debug APK on push and publishes
it on v* tags.

## 2026-10-05 423567e Fork Sentinela: allowlist por contato, midia so de permitidos, limpeza automatica, sem Firebase

## 2026-08-19 2574953 Documented the edge to edge insets setup

## 2026-08-19 aeca93f Made the app properly edge to edge instead of opting out

## 2026-08-19 60f7e08 Noted that deletion detection is best effort

## 2026-08-19 2ec856c Hid the bundled x new messages notification from the chat list

## 2026-08-19 12fa795 Fixed race condition causing duplicate messages

## 2026-08-18 638fee5 Added CLAUDE.md

## 2026-08-18 d133147 Removed dead code and fixed stale package name in test

## 2026-08-18 fed6755 Polished the empty chat list state

## 2026-08-18 04080f3 Added a deleted message badge and fixed it leaking onto recycled views

## 2026-08-18 9ff0733 Fixed dark theme overrides being ignored

## 2026-08-18 bec6274 Fixed deleted messages never being detected

## 2025-10-28 dd80e0e Released version 1.3.0

## 2025-10-14 1e101e0 Removed sample data

## 2025-10-14 ede9070 Grouping chats by date

## 2025-10-14 8935144 Removed BroadcastReceiver

## 2025-10-14 53cd214 Disabled proguard when in debug mode

## 2025-10-14 d59e3ef Opt out EdgeToEdge Enforcement

## 2025-10-14 fa6dcbc Updated gradle to the latest version

## 2025-10-14 cf9312e Fixed BroadcasterReceiver issue

## 2025-10-14 3d38c7d Updated grade and kotlin versions

## 2025-10-14 b495d1e Changed MinSDK to 23

## 2025-10-14 aca37b7 Downgraded Firebase bom

## 2025-10-13 6807845 Room schema

## 2025-10-13 9fee605 Changed targetSdk

## 2025-10-13 8bba24e Updated dependencies

## 2022-10-29 563a11a Updated dependencies

## 2022-08-17 f402458 Finishing intro if the policy is respected

## 2022-08-17 2630fc8 Create mobsf.yml

## 2022-08-17 d972942 Changed Target SDK version

## 2022-08-17 7d5602f Fixed Chip View hiding issue

## 2022-08-17 a84a79a Updated dependencies

## 2022-08-15 749fd31 Released version 1.2.0

## 2022-08-15 9d273cf Updated screenshots

## 2022-08-15 ed92de7 checking duplicate message

## 2022-08-15 831b20e Add custom toolbar and changed dark mode colors

## 2022-08-15 f166a22 Changed color

## 2022-08-15 aee1e85 Removed json

## 2022-08-15 9420717 Hiding the Chip view if the app type is null

## 2022-08-15 7a45565 Inspecting code

## 2022-08-15 9bf72ef Delete google-services.json

## 2022-08-15 78f6841 Add new titles to ignore

## 2022-08-15 55eac5b Update GitIgnore file

## 2022-08-15 9319a59 Updated README.md

## 2022-08-15 d7acdfb Ignore google-service file

## 2022-08-15 b62ed52 Updated

## 2022-08-15 1c74b2d Removed Google service file

## 2022-08-13 b10dcb1 Add new titles to ignore

## 2022-08-13 b7f053d Add click ripple effect

## 2022-08-13 eb6e611 Add Fragment ktx

## 2022-08-13 c6fbbb0 Updated dependencies

## 2022-08-13 f46fbed Add new feature: Now the app supports (WhatsApp,WhatsApp business,Signal and Telegram)

## 2022-08-12 a14d71d Improved the code

## 2022-07-01 843a3c9 Removed target API

## 2022-07-01 5456e4f Changed the text color

## 2022-07-01 169f8d1 Added new color

## 2022-06-20 03ce536 Added play store link

## 2022-06-20 97a88f5 Released version 1

## 2022-06-19 b7eedf1 Disabled Crashlytics collection

## 2022-06-19 67b21e5 Added Junit testing dependency

## 2022-06-19 8a7c20f Removed converters class

## 2022-06-19 b6d02f6 Inspecting the code

## 2022-06-19 79e9d05 Hiding empty message if data gets changed

## 2022-06-18 a37591d Added Into slides

## 2022-06-18 7a87610 Added function to Start activities with animation

## 2022-06-18 9ba0c08 Added Toast Extension

## 2022-06-15 32fb535 Fixed service unregister issue

## 2022-06-13 6ac0bb3 Moved to new package

## 2022-06-13 3ee7ec3 Added AppIntro

## 2022-06-13 3973291 Updated the dependencies

## 2022-06-13 fd38702 Updated ReadMe.md

## 2022-06-13 986d450 Room Schema

## 2022-06-13 9918bc4 Added chat icon

## 2022-06-13 248b4df Added image loading extension

## 2022-06-13 8e0fc1e Added new string value

## 2022-06-13 3ee2717 Improved the code

## 2022-06-13 e342ce3 Updated sample data

## 2022-06-09 c4d9d7c Update README.md

## 2022-06-08 ed996fc Added new screenshot

## 2022-06-08 975fc80 Updated Chat backgound

## 2022-06-08 78fef1c Added chat background

## 2022-06-08 36983be Added textView

## 2022-06-08 b553565 Show message if there is no data

## 2022-06-08 9a85782 Changed Bottom navigation bar color

## 2022-06-08 ecc9b45 Set dialog not cancelable

## 2022-06-08 6db1dbf Added schemaLocation

## 2022-06-08 8a810af Added Glide dependency

## 2022-06-07 59a6479 Improved Screenshots

## 2022-06-07 712d04d Updated Screenshots

## 2022-06-07 6c34ec5 Added Splash Screen

## 2022-06-07 d8355a2 Validating Notification title

## 2022-06-06 fb4a92d Updated Android gradle plugin

## 2022-06-05 4c13b38 Updated dependencies

## 2022-06-05 78a5323 Enabled Proguard

## 2022-06-05 2ef024c Added Constants

## 2022-06-05 dd41d35 Added extension for Json conversion

## 2022-06-05 e5bc3a7 Added Extensions for Json convertion

## 2022-05-28 e521dc6 Update README.md

## 2022-05-25 2c7f9cc Changed title size

## 2022-05-25 4bb716b Added download link

## 2022-05-25 3c02e90 Added Screenshots to the Readme

## 2022-05-25 b4fdc3d Added Screenshots

## 2022-05-25 51d51aa Display date if the time is more than 48 hours

## 2022-05-25 82ff6f5 Fixed nullability issue

## 2022-05-25 e03998c Comparing hours between two dates

## 2022-05-25 465f0f9 Updated Gradle version

## 2022-05-05 c7d74cd Disabling crashlytics if app is in Debug Mode

## 2022-04-21 a3f919f Changed FontSize

## 2022-04-21 f90a261 Set clickable link and added link color

## 2022-04-21 21391dd Checking if title is valid

## 2022-04-21 f3ef531 Added new attribute

## 2022-04-21 8a5a4e3 Revert "Added dots" This reverts commit 8d33c20c

## 2022-04-21 4be4a8a Revert "Added dots" This reverts commit 8d33c20c

## 2022-04-21 8d33c20 Added dots

## 2022-04-21 236d309 Fixed name issue

## 2022-04-21 5a76767 Added new title to ignore

## 2022-04-21 42b8a19 Removed text style

## 2022-04-21 afc478f Changed primary colors

## 2022-04-21 10c5a8c Improved the code

## 2022-04-21 0e8480a Navigate to Chat detail from Notification click

## 2022-04-21 1b1d854 Changed notification icon

## 2022-04-21 b743fd3 Changing the background of deleted message

## 2022-04-21 dc17814 Removed message from the subtitle

## 2022-04-21 76922e4 Changed App icon

## 2022-04-21 5a87bc7 Removed space before the name

## 2022-04-19 afb12e6 Added loading

## 2022-04-19 6a0b45d Changed Functions to variables

## 2022-04-19 0516f92 Added Night colors

## 2022-04-19 885e0d3 Changed message background color

## 2022-04-18 febd5f6 Added Crashlytics

## 2022-04-18 d1fca55 Added Firebase

## 2022-04-18 0ce3ba7 Updated dependencies

## 2022-04-18 afdffe5 Improved the code

## 2022-04-18 85da57b Fetching all data

## 2022-04-18 268245b Fetched chat list order by time

## 2022-03-18 bb8ec41 Added new titles to ignore saving

## 2022-03-18 addadae Displaying date and time

## 2022-03-17 a9b2568 Added Group chat message

## 2022-03-16 648f4bd Changed Name

## 2022-03-16 f7cfa91 Changed Intent Namespace

## 2022-03-16 a9a27d6 Changed App Name

## 2022-03-14 dae4bc2 Changed app name

## 2022-03-13 b982c02 Comparing Date

## 2022-03-13 0947d85 Set label app name

## 2022-03-13 d002740 Displaying user in toolbar title

## 2022-03-13 7f72536 Changed life cycle owner

## 2022-03-13 1625b05 Updated dependencies

## 2022-03-13 61f2eaf Added new string

## 2022-03-13 5d39341 Changed font family, font size

## 2022-03-13 1b34ad2 Added fragment back button

## 2022-03-12 decf0e3 Added back button

## 2022-03-12 9c05b8d Removed Activities and added Fragments

## 2022-03-10 5f35abf Fixed deleted message issue

## 2022-03-10 6fcdfcc Notifying user if message was deleted

## 2022-03-09 212c5d6 Added background drawable

## 2022-03-09 e00f4f5 Removed unused code

## 2022-03-09 44902ea Moved to new Package

## 2022-03-09 9ae1279 Changed order

## 2022-03-08 eb629d4 Removed GlobalScope and added ProcessLifecycleOwner

## 2022-03-08 3d3c5cf Saving notifications when the app is closed

## 2022-03-07 4c35100 Fetching messages by user

## 2022-03-07 c35b5d6 Added chat details

## 2022-03-07 62af267 Added click listener

## 2022-03-07 0d3f96d Changed parent layout

## 2022-03-07 e6ceb70 Displaying chat list

## 2022-03-07 395bb56 Fixed duplicate Message issue

## 2022-03-07 1492fa8 Changed time to Long

## 2022-03-07 05b62dc Removed Logs

## 2022-03-07 84fffda Renamed Model from Message to Chat

## 2022-03-07 1243df0 Removed chat

## 2022-03-06 be3d083 Added Entity to the database

## 2022-03-06 6c5d71c Added Random ID

## 2022-03-06 8ca5cea Added time

## 2022-03-06 4a29fe3 Added Conflict Strategy

## 2022-03-06 e546e11 Fetching and saving messages

## 2022-03-06 b267a56 Ignoring Notifications from other Apps

## 2022-03-06 aa6e20f Added Converter

## 2022-03-06 ebe21e3 Added Gson dependency

## 2022-03-06 9a19bbb Added Converters

## 2022-02-14 22167d3 improved

## 2022-02-14 eb6fe12 Removed slash

## 2022-02-14 c2f520a Removed Id and set time PrimaryKey

## 2022-02-14 3081bbc Added DateExtension to convert long to String

## 2022-02-14 dec5c79 Order by time

## 2022-02-14 88ce5e3 Initial commit

## 2022-02-14 58f6bcb Saving Message to the database

## 2022-02-13 48368a1 Added Room db and Dagger hilt

## 2022-02-13 678dbf3 Initial commit
