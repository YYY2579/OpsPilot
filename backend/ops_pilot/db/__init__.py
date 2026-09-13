"""数据库访问层。

凭据解析（credentials）与连接执行（client）分层：工具 Executor 只依赖
DbRunner 协议 + DbCredentialResolver，单测注入假 Runner 即可，不需要真实数据库。
"""
