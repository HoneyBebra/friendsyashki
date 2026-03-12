# Generate pb2-files:

from source directory

```shell
python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  src/gRPC/protos/user.proto
```
