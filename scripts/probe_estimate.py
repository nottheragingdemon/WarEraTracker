"""One-off: compare employee.getCompanyEstimate with each company's listed workers/wages (official API only)."""
import os, sys
os.environ["WARERA_GATEWAY"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wartrack.api import Client
USERS = ['6a089421e04251b8ffa71a61', '6a1403f53748edf2084fa328', '6ae6e4cbc81938524225df65', '699764069ba1e83d02645548', '6a336af4597cadab683a4cf6', '6acd7a5a7d12e9aa392a69a9', '6afb80786574904a2de2e113', '6ac394c5c8a508fbd1aa2bba', '6a3a25b31cd8e80b69a4851c', '6a6b5824a4d1b7f58f39848a', '6aa9732c68941f76c9a0aea0', '6a4957f0a03143eb6a80351d', '697a102151ca516071833076', '69bd1c5f3623bca880b29c94', '699da7941ee17a2f8e388c56', '6b00e1743a9402f85a77c9db', '699d99a1d70af7f97531caa8', '6ac693a4e05c56fdd5ca7075', '682f3081b7511e36ed61bda2', '6aabe8e2df15e9b70342f194', '69b281dd2895f070b7a0c278', '69ccde9f1a1f9166480a8b26', '6afd48c5751e7f0d5322e1a6', '699c237398649317605f029b', '693f5427a4c9b5b39c783077', '6af52157ec2b0f8744689560', '6acd24e3c6dc3525cf0f103a', '6a12d046ec69e28c2eb5f238', '68b2bd6b21546021116872a5', '6a6a867276536fe6ddce6179', '6950af6ff49d536da4e74293', '69c3ba64853edc66e4b6d1d1', '69b41267a08441c71eb3c919', '69d7a15dfd0b49813f12d101', '69d465de700d67c609d3b8d9', '6b007ca2c4d979da7d307de2', '69f9b6bb610c6907eace7466', '68a7899959ebef35173a6a95', '6a2136c3bca78680d0dcbd8d', '69d939a21ca1408e1d9469e8', '6ad4f7f93f505f6fa4c966a7', '6b003fba352772a9f9901827', '6a2d05fae9f065a004a12afc', '6a500cd2f7963e35638240b7', '6afbc1817ad4388ffb962fb0', '697d62fb3241f8b0eb4de834', '6a030663a2841fd2fff14dab', '699c9cd0e4b4639a8b624243', '6aeefaae2ea1b2c5de563e20', '699dae9c19024e8057615a6d', '6a70fc5e2aec02cc2cec0675', '6a988b1a7428764164c64e78', '6ab21a478421990d91bdfa40', '6a9c9dd0157b079d9f700f49', '699216c460e5bc94b0e43d58', '6af70ed50fa86b235374fbe3', '6829c71bf9fe6076b38a5379', '6b0220f1942dc44cc5122193', '69ea0e620f5ff8138cb47251', '697f8ff192b5608af22e001a', '68387b68d7a1d13b3c91e728', '6855b3242c7799fdf9f4ab85', '68cce5bae7e7542a697dd0f8', '6ae380d3a279aa14d023ca48', '6a9c250941c34849b7fd045b', '698b95b8305278d0853b51df', '69233fa1d9075fc1db6830ac', '6885621c4838016a71c1983e', '6af84c61f969df4006b3e38c', '69ece875c935523ef74d12f9', '6adc36e7b4506852c53291e1', '6a7ea3e408217520827bb378', '6872694c80d2db2a8e1f0e26', '6adc797c988e0f585c1e9e2d', '69fe1212f0567f3aa55c649d', '6a4c9957d8321540a93ce97d', '688c3e804f7299ac68496349', '6a5dc3737672743424c9d563', '6a11e057626278b72f8defd3', '6ae8c885162e6fc748837c10']
c = Client()
rows = []
for u in USERS:
    try:
        d = c.call("company.getCompanies", userId=u, perPage=20)
    except Exception:
        continue
    for cid in d["items"]:
        co = c.call("company.getById", companyId=cid)
        if co.get("disabledAt"):
            continue
        try:
            e = c.call("employee.getCompanyEstimate", companyId=cid)
        except Exception as ex:
            e = {"err": str(ex)[:80]}
        ws = co.get("workers") or []
        rows.append((cid, co.get("itemCode"), len(ws), round(sum(w["wage"] for w in ws), 4), e))
    if len(rows) >= 45:
        break
print("id item nWorkers sumWages | estimate")
for r in rows:
    print(r[0][-6:], r[1], r[2], r[3], "|", {k: v for k, v in r[4].items() if k != "ifEnabled"}, ("IFENABLED" if "ifEnabled" in r[4] else ""))
