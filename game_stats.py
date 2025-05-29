import requests
import logging
import json
import traceback
from datetime import datetime, timedelta
import urllib.parse

class GameStats:
    def __init__(self, game_api):
        """初始化游戏统计类
        
        Args:
            game_api: GameAPI实例，用于获取LCU API的基础URL
        """
        self.game_api = game_api
        self.url = game_api.url
        self.summoner_id = game_api.summoner_id
    
    def get_current_game_players(self):
        """获取当前游戏中的所有玩家信息"""
        try:
            # 首先检查是否在游戏中
            session_response = requests.get(
                f"{self.url}/lol-gameflow/v1/session",
                verify=False
            )
            
            
            if session_response.status_code != 200:
                logging.debug("当前不在游戏中")
                return None
            
            # 获取当前游戏会话信息
            response = requests.get(
                f"{self.url}/lol-champ-select/v1/session",
                verify=False
            )
            
            
            if response.status_code != 200:
                logging.error(f"获取当前游戏玩家信息失败: {response.status_code}")
                return None
            
            data = response.json()
            players = []
            
            # 获取所有玩家信息
            for member in data.get("myTeam", []):
                player = {
                    "summonerId": member.get("summonerId"),
                    "puuid": member.get("puuid"),
                    "summonerName": member.get("summonerName"),
                    "championId": member.get("championId"),
                    "position": member.get("assignedPosition", "未知")
                }
                if player.get("puuid"):
                    summoner_info = self.get_summoner_by_puuid(player["puuid"])
                    if summoner_info and summoner_info.get("displayName"):
                        player["summonerName"] = summoner_info["displayName"]
                    elif summoner_info and summoner_info.get("gameName") and summoner_info.get("tagLine"):
                         player["summonerName"] = f"{summoner_info['gameName']}#{summoner_info['tagLine']}"
                    elif player.get("summonerId") and player["summonerId"] != 0:
                         summoner_info_by_id = self.get_summoner_by_id(player["summonerId"])
                         if summoner_info_by_id and summoner_info_by_id.get("displayName"):
                             player["summonerName"] = summoner_info_by_id["displayName"]
                         elif summoner_info_by_id and summoner_info_by_id.get("gameName") and summoner_info_by_id.get("tagLine"):
                             player["summonerName"] = f"{summoner_info_by_id['gameName']}#{summoner_info_by_id['tagLine']}"

                players.append(player)
                logging.debug(f"添加玩家信息: {player}")
            
            logging.info(f"成功获取 {len(players)} 个玩家信息")
            return players
            
        except Exception as e:
            logging.error(f"获取当前游戏玩家信息时出错: {e}")
            logging.error(f"完整错误信息: {str(e)}")
            logging.error(f"错误堆栈: {traceback.format_exc()}")
            return None
    
    def get_player_match_history(self, summoner_id, count=10, mode=None):
        """获取玩家最近的比赛记录，支持按模式过滤"""
        try:
            # 首先获取召唤师的puuid
            summoner_response = requests.get(
                f"{self.url}/lol-summoner/v1/summoners/{summoner_id}",
                verify=False
            )
            if summoner_response.status_code != 200:
                logging.error(f"获取召唤师信息失败: {summoner_response.status_code}")
                return []
            summoner_data = summoner_response.json()
            puuid = summoner_data.get("puuid")
            if not puuid:
                logging.error(f"无法获取召唤师PUUID")
                return []
            # 使用puuid获取比赛历史
            matchlist_response = requests.get(
                f"{self.url}/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=29",
                verify=False
            )
            if matchlist_response.status_code != 200:
                logging.error(f"获取比赛列表失败: {matchlist_response.status_code}")
                return []
            matchlist_data = matchlist_response.json()
            if not matchlist_data or "games" not in matchlist_data:
                logging.error("比赛历史数据格式错误")
                return []
            # 模式映射
            queue_map = {
                'SOLO_DUO': 420,
                'FLEX': 440,
                'ARAM': 450,
                'URF': 900,
                'PRACTICETOOL': 1700
            }
            # 过滤并处理游戏列表
            matches = []
            for game in matchlist_data["games"]["games"]:
                # 按模式过滤
                if mode and mode != 'ALL':
                    if mode in ['SOLO_DUO', 'FLEX']:
                        if game.get("queueId") != queue_map[mode]:
                            continue
                    else:
                        if game.get("gameMode") != mode:
                            continue
                try:
                    participant = game["participants"][0]
                    stats = participant.get("stats", {})
                    kills = stats.get("kills", 0)
                    deaths = stats.get("deaths", 0)
                    assists = stats.get("assists", 0)
                    kda = (kills + assists) / deaths if deaths > 0 else kills + assists
                    duration_minutes = game["gameDuration"] // 60
                    duration_seconds = game["gameDuration"] % 60
                    game_duration = f"{duration_minutes}:{duration_seconds:02d}"
                    game_time = datetime.fromtimestamp(game["gameCreation"] / 1000)
                    game_time_str = game_time.strftime("%m-%d %H:%M")
                    champion_id = participant.get("championId")
                    champion_name = self.game_api.get_champion_alias(champion_id) if champion_id else "未知英雄"
                    match_data = {
                        "gameId": game.get("gameId"),
                        "gameCreation": game_time_str,
                        "championName": champion_name,
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "kda": round(kda, 2),
                        "win": stats.get("win", False),
                        "gameDuration": game_duration,
                        "gameMode": game.get("gameMode", "未知模式"),
                        "queueId": game.get("queueId", 0)
                    }
                    matches.append(match_data)
                except (KeyError, IndexError) as e:
                    logging.error(f"处理比赛数据时出错: {e}")
                    continue
            # 只取最新count场
            matches = matches[:count]
            return matches
        except Exception as e:
            logging.error(f"获取比赛历史失败: {e}")
            logging.error(f"错误堆栈: {traceback.format_exc()}")
            return []
    
    def get_teammates_stats(self, mode=None):
        """获取当前游戏中所有队友的最近战绩，支持模式过滤"""
        try:
            # 首先尝试获取自己的战绩
            if self.summoner_id:
                match_history = self.get_player_match_history(self.summoner_id, mode=mode)
                if match_history:
                    my_stats = [{
                        "summonerName": "我的战绩",
                        "championId": None,
                        "position": None,
                        "matchHistory": match_history
                    }]
            # 尝试获取当前游戏玩家信息
            players = self.get_current_game_players()
            if not players:
                return my_stats if 'my_stats' in locals() else None
            teammates_stats = []
            has_teammates = False
            for player in players:
                summoner_id = player.get("summonerId")
                if summoner_id and summoner_id != self.summoner_id:
                    has_teammates = True
                    match_history = self.get_player_match_history(summoner_id, mode=mode)
                    if match_history:
                        teammates_stats.append({
                            "summonerName": player.get("summonerName"),
                            "championId": player.get("championId"),
                            "position": player.get("position"),
                            "matchHistory": match_history
                        })
            if not has_teammates and 'my_stats' in locals():
                return my_stats
            return teammates_stats if teammates_stats else None
        except Exception as e:
            logging.error(f"获取战绩时出错: {e}")
            if 'my_stats' in locals():
                return my_stats
            return None
    
    def get_match_history_by_summoner_name_and_mode(self, summoner_name, count=10, mode=None):
        """根据召唤师名字和模式获取玩家最近的比赛记录"""
        try:
            summoner_data = self.get_summoner_by_name(summoner_name)
            if not summoner_data or 'summonerId' not in summoner_data:
                logging.error(f"无法找到召唤师 {summoner_name} 或获取其 Summoner ID")
                return None
            summoner_id = summoner_data['summonerId']
            logging.info(f"成功获取 Summoner ID: {summoner_id} for {summoner_name}")
            # 直接调用 get_player_match_history 方法，传递 Summoner ID 和模式
            return self.get_player_match_history(summoner_id, count, mode)
        except Exception as e:
            logging.error(f"根据召唤师名字和模式获取比赛历史失败: {e}")
            import traceback
            logging.error(f"错误堆栈: {traceback.format_exc()}")
            return None
    
    def get_match_detail(self, game_id):
        """获取指定对局的详细信息，包括所有参与者的英雄、装备等"""
        try:
            response = requests.get(
                f"{self.url}/lol-match-history/v1/games/{game_id}",
                verify=False
            )
            if response.status_code != 200:
                logging.error(f"获取对局详情失败: {response.status_code}")
                return None
            data = response.json()
            # 构建 participantId -> summonerId 和 participantId -> gameName 映射
            id_to_summoner_id = {}
            id_to_name = {}
            for identity in data.get("participantIdentities", []):
                pid = identity.get("participantId")
                player = identity.get("player", {})
                if pid and player:
                    id_to_summoner_id[pid] = player.get("summonerId")
                    id_to_name[pid] = player.get("gameName", "")

            # 先统计全队对英雄伤害和全队金钱
            total_team_champ_damage = 0
            total_team_gold = 0
            for p in data.get("participants", []):
                stats = p.get("stats", {})
                total_team_champ_damage += stats.get("totalDamageDealtToChampions", 0)
                total_team_gold += stats.get("goldEarned", 0)
            participants = []
            for p in data.get("participants", []):
                participant_id = p.get("participantId")
                stats = p.get("stats", {})
                summoner_name = id_to_name.get(participant_id, "未知召唤师")
                champion_id = p.get("championId")
                champion_name = self.game_api.get_champion_alias(champion_id) if champion_id else "未知英雄"
                spells = [p.get("spell1Id"), p.get("spell2Id")]
                items = []
                for i in range(7):
                    item_id = stats.get(f"item{i}")
                    if item_id and item_id != 0:
                        items.append(item_id)
                kills = stats.get("kills", 0)
                deaths = stats.get("deaths", 0)
                assists = stats.get("assists", 0)
                win = stats.get("win", False)
                kda = (kills + assists) / max(deaths, 1)
                total_damage = stats.get("totalDamageDealt", 0)
                champ_damage = stats.get("totalDamageDealtToChampions", 0)
                gold_earned = stats.get("goldEarned", 0)
                minions_killed = stats.get("totalMinionsKilled", 0) + stats.get("neutralMinionsKilled", 0)
                # 伤害占比和经济占比
                damage_ratio = champ_damage / total_team_champ_damage if total_team_champ_damage else 0
                gold_ratio = gold_earned / total_team_gold if total_team_gold else 0
                # 伤转 伤害占比/经济占比
                damage_conversion = round(damage_ratio / gold_ratio, 2) if gold_ratio else 0
                damage_to_turrets = stats.get("damageDealtToTurrets", 0)
                self_mitigated = stats.get("damageSelfMitigated", 0)
                participant = {
                    "summonerName": summoner_name,
                    "championId": champion_id,
                    "championName": champion_name,
                    "spells": spells,
                    "items": items,
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "kda": round(kda, 2),
                    "win": win,
                    "totalDamage": total_damage,
                    "champDamage": champ_damage,
                    "goldEarned": gold_earned,
                    "minionsKilled": minions_killed,
                    "damageConversion": damage_conversion,
                    "damageRatio": round(damage_ratio, 2),
                    "goldRatio": round(gold_ratio, 2),
                    "damageToTurrets": damage_to_turrets,
                    "damageSelfMitigated": self_mitigated,
                    "summonerId": id_to_summoner_id.get(participant_id)
                }
                participants.append(participant)
            return {
                "gameId": game_id,
                "gameCreation": data.get("gameCreation"),
                "gameDuration": data.get("gameDuration"),
                "gameMode": data.get("gameMode"),
                "participants": participants
            }
        except Exception as e:
            logging.error(f"获取对局详情时出错: {e}")
            return None 

    def get_summoner_by_puuid(self, puuid):
        """根据玩家puuid获取召唤师信息"""
        try:
            # 检查PUUID格式是否有效，防止Invalid URI Format错误
            if not puuid or '-' not in puuid or len(puuid) < 30:
                logging.warning(f"无效的PUUID格式: {puuid}")
                return None
            
            # 对PUUID进行URL编码，防止特殊字符导致的错误
            encoded_puuid = urllib.parse.quote(puuid)
            
            response = requests.get(
                f"{self.url}/lol-summoner/v1/summoners/by-puuid/{encoded_puuid}",
                verify=False
            )
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"根据puuid获取召唤师信息失败: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logging.error(f"根据puuid获取召唤师信息时出错: {e}")
            import traceback
            logging.error(f"错误堆栈: {traceback.format_exc()}")
            return None

    def get_summoner_by_id(self, summoner_id):
        """根据玩家summonerId获取召唤师信息"""
        # 注意：这个方法可能在某些模式下（如训练模式）summonerId为0时不可用
        if summoner_id == 0:
             return None
        try:
            response = requests.get(
                f"{self.url}/lol-summoner/v1/summoners/{summoner_id}",
                verify=False
            )
            if response.status_code == 200:
                return response.json()
            else:
                # 记录错误，但可能在预期之内（如summonerId为0）
                logging.debug(f"根据summonerId获取召唤师信息失败: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logging.error(f"根据summonerId获取召唤师信息时出错: {e}")
            import traceback
            logging.error(f"错误堆栈: {traceback.format_exc()}")
            return None 