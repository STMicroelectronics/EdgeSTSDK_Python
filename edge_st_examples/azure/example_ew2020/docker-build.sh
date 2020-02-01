# Changelog label versions
# stmedge.azurecr.io/modaievt_tpgw:0.0.1-arm32v7 --> first version
# stmedge.azurecr.io/modaievt_tpgw:0.0.2-arm32v7 --> use python3, BlueST-SDK-v1.4.0 and setAlgo method and dependencies/related

#docker build  --rm -f ./Dockerfile.arm32v7 -t stmedge.azurecr.io/modaievt_tpgw:0.0.2-arm32v7 . && docker push stmedge.azurecr.io/modaievt_tpgw:0.0.2-arm32v7

##0.0.2 version was running prior to changes with AIAllAlgoDetails API
#docker build  --rm -f ./Dockerfile.arm32v7 -t stm32containerregistry.azurecr.io/modaievt_tpgw:0.0.2-arm32v7 . && docker push stm32containerregistry.azurecr.io/modaievt_tpgw:0.0.2-arm32v7

#docker build  --rm -f ./Dockerfile.arm32v7 -t stm32containerregistry.azurecr.io/modaievt_tpgw:0.0.3-arm32v7 . && docker push stm32containerregistry.azurecr.io/modaievt_tpgw:0.0.3-arm32v7
# Container for EW2020
docker build  --rm -f ./Dockerfile.arm32v7 -t stm32containerregistry.azurecr.io/mod_ew2020:0.3 . && docker push stm32containerregistry.azurecr.io/mod_ew2020:0.3

