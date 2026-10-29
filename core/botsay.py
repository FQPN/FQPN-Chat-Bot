"""1.14.0: the built-in commands answer in the app's language. Their texts stay English in the code; this turns each one
into Arabic when the app is in Arabic (Settings > Appearance > Language). Anything not in the table stays as it is."""
import re

AR = [
    (r"📋 Commands: (.+)", r"📋 الأوامر: \1"),
    (r"Commands: none yet", r"الأوامر: لا توجد أوامر بعد"),
    (r"Commands: (.+)", r"الأوامر: \1"),
    (r"Title: (.*)", r"العنوان: \1"),
    (r"Game: (.*)", r"اللعبة: \1"),
    (r"Title updated to: (.*)", r"تم تغيير العنوان إلى: \1"),
    (r"Game updated to: (.*)", r"تم تغيير اللعبة إلى: \1"),
    (r"Couldn't change the title\. Reconnect Twitch to grant the new permission\.", r"تعذّر تغيير العنوان. أعد ربط تويتش لمنح الصلاحية الجديدة."),
    (r"Couldn't change the game\. Reconnect Twitch to grant the new permission\.", r"تعذّر تغيير اللعبة. أعد ربط تويتش لمنح الصلاحية الجديدة."),
    (r"Couldn't find a game called '(.*)' on Twitch\.", r"لم أجد لعبة باسم «\1» في تويتش."),
    (r"Chatbot app: (.+)", r"برنامج البوت: \1"),
    (r"(@\S+ )?Command (\S+) added\.", r"\1تمت إضافة الأمر \2."),
    (r"(@\S+ )?Command (\S+) updated\.", r"\1تم تعديل الأمر \2."),
    (r"(@\S+ )?Command (\S+) deleted\.", r"\1تم حذف الأمر \2."),
    (r"(@\S+ )?Alias (\S+) removed\.", r"\1تم حذف الاسم البديل \2."),
    (r"(@\S+ )?Give the command a name\.", r"\1اكتب اسم الأمر."),
    (r"(@\S+ )?Command names can be at most (\d+) characters\.", r"\1اسم الأمر يمكن أن يكون \2 حرفًا كحد أقصى."),
    (r"(@\S+ )?'(.*)' is a built-in command and can't be used as a name\.", r"\1«\2» أمر مدمج ولا يمكن استخدامه كاسم."),
    (r"(@\S+ )?'(.*)' is already used by another command\.", r"\1«\2» مستخدم في أمر آخر."),
    (r"(@\S+ )?Unknown user level '(.*)'\. Use: (.*)\.", r"\1مستوى غير معروف «\2». استخدم: \3."),
    (r"(@\S+ )?-cd needs a number of seconds, like -cd=30\.", r"\1-cd يحتاج عدد ثوانٍ، مثل -cd=30."),
    (r"(@\S+ )?-a needs an alias, like -a=!dc\.", r"\1-a يحتاج اسمًا بديلًا، مثل -a=!dc."),
    (r"(@\S+ )?(\S+) doesn't exist\.", r"\1الأمر \2 غير موجود."),
    (r"(@\S+ )?Usage: !cmadd (.*)", r"\1الطريقة: !cmadd \2"),
    (r"(@\S+ )?(\S+) already exists\. Use !cmedit to change it\.", r"\1الأمر \2 موجود. استخدم !cmedit لتعديله."),
    (r"(@\S+ )?Add the game after -a=!setgame, like: (.*)", r"\1اكتب اللعبة بعد -a=!setgame، مثل: \2"),
    (r"(@\S+ )?Add the title after -a=!settitle\.", r"\1اكتب العنوان بعد -a=!settitle."),
    (r"(@\S+ )?Add the response after the options\.", r"\1اكتب الرد بعد الخيارات."),
    (r"(@\S+ )?A command can't be its own alias\.", r"\1لا يمكن أن يكون الأمر اسمًا بديلًا لنفسه."),
    (r"(@\S+ )?Usage: !cmedit name \[options\] new response", r"\1الطريقة: !cmedit الاسم [الخيارات] الرد الجديد"),
    (r"(@\S+ )?Options only: -ul=, -cd= or -a=\. Use edit to change the response\.", r"\1الخيارات فقط: -ul= أو -cd= أو -a=. استخدم edit لتغيير الرد."),
    (r"(@\S+ )?Add the game or title after -a=!setgame / -a=!settitle\.", r"\1اكتب اللعبة أو العنوان بعد -a=!setgame / -a=!settitle."),
    (r"(@\S+ )?Nothing to change\. Give a new response or options\.", r"\1لا يوجد ما يتغير. اكتب ردًا جديدًا أو خيارات."),
    (r"(@\S+ )?Usage: !cmdel name", r"\1الطريقة: !cmdel الاسم"),
    (r"(@\S+ )?(\S+) is a mini game command\. Choose another name\.", r"\1«\2» أمر لعبة. اختر اسمًا آخر."),
]
_AR = [(re.compile(p + r"\Z", re.S), r) for p, r in AR]


def tr(text: str, lang: str) -> str:
    """The built-in answer in the app's language ("ar" or "en")."""
    if lang != "ar":
        return text
    for rx, rep in _AR:
        if rx.match(text):
            return rx.sub(rep, text, count=1)
    return text
