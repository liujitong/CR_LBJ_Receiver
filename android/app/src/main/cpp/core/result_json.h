// result_json.h — DecodeResult → JSON（engine 回调与 lbj_cli 对拍共用，保证逐字段一致）
// 字段名与桌面版 Python DecodeResult.toDict() 完全同名
#pragma once
#include <string>
#include "decoder.h"

namespace lbj {

std::string resultToJson(const LbjResult& r);

} // namespace lbj
