import urllib.request

url = "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzFmNDQwYzk5NTEwNjQ3ODhhODAxZTE3ZWY5YTNjNmQ2EgsSBxDcgejTvwMYAZIBJAoKcHJvamVjdF9pZBIWQhQxNTMwNzM5NzM0MDQ3Nzk5NzUxNw&filename=&opi=96797242"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    html = response.read()
    with open("dashboard_stitch.html", "wb") as f:
        f.write(html)
print("Saved to dashboard_stitch.html")
