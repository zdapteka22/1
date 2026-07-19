AddCSLuaFile()

ENT.Base = "base_nextbot"
ENT.Type = "nextbot"
ENT.PrintName = "Los Minions"
ENT.Author = "Los Minions"
ENT.Category = "Los Minions Nextbot"
ENT.Spawnable = true
ENT.AdminOnly = false

-- Preferred compiled Source model from minions.glb
local PREFERRED_MODEL = "models/los_minions/minions.mdl"
-- Fallback until GLB is compiled to .mdl
local FALLBACK_MODEL = "models/player/kleiner.mdl"

local CHASE_SOUNDS = {
	"los_minions/chase1.mp3",
	"los_minions/chase2.mp3",
	"los_minions/banana.mp3"
}

local IDLE_SOUNDS = {
	"los_minions/idle1.mp3",
	"los_minions/idle2.mp3"
}

local JUMPSCARE_SOUND = "los_minions/jumpscare.mp3"

function ENT:Initialize()
	if util.IsValidModel(PREFERRED_MODEL) then
		self:SetModel(PREFERRED_MODEL)
	else
		self:SetModel(FALLBACK_MODEL)
	end

	self.LoseTargetDist = 3500
	self.SearchRadius = 2500
	self.WalkSpeed = 120
	self.RunSpeed = 520
	self.NextSound = 0
	self.Enemy = nil

	self:SetHealth(9999)
	self:SetCollisionGroup(COLLISION_GROUP_NPC)
end

function ENT:SetEnemy(ent)
	self.Enemy = ent
end

function ENT:GetEnemy()
	return self.Enemy
end

function ENT:PlayNextbotSound(listOrPath)
	if CurTime() < (self.NextSound or 0) then return end

	local path = listOrPath
	if istable(listOrPath) then
		if #listOrPath == 0 then return end
		path = listOrPath[math.random(#listOrPath)]
	end

	if not path or path == "" then return end

	self:EmitSound(path, 80, 100, 1, CHAN_VOICE)
	self.NextSound = CurTime() + 3
end

function ENT:HaveEnemy()
	local enemy = self:GetEnemy()

	if IsValid(enemy) then
		if self:GetRangeTo(enemy:GetPos()) > self.LoseTargetDist then
			return self:FindEnemy()
		end

		if enemy:IsPlayer() and not enemy:Alive() then
			return self:FindEnemy()
		end

		return true
	end

	return self:FindEnemy()
end

function ENT:FindEnemy()
	local nearby = ents.FindInSphere(self:GetPos(), self.SearchRadius)

	for _, ent in ipairs(nearby) do
		if ent:IsPlayer() and ent:Alive() then
			self:SetEnemy(ent)
			return true
		end
	end

	self:SetEnemy(nil)
	return false
end

function ENT:OnContact(ent)
	if not IsValid(ent) or not ent:IsPlayer() then return end
	if not ent:Alive() then return end

	self:EmitSound(JUMPSCARE_SOUND, 90, 100, 1, CHAN_VOICE)
	ent:TakeDamage(25, self, self)
end

function ENT:ChaseEnemy(options)
	options = options or {}

	local path = Path("Follow")
	path:SetMinLookAheadDistance(options.lookahead or 300)
	path:SetGoalTolerance(options.tolerance or 40)

	local enemy = self:GetEnemy()
	if not IsValid(enemy) then return "failed" end

	path:Compute(self, enemy:GetPos())
	if not path:IsValid() then return "failed" end

	while path:IsValid() and self:HaveEnemy() do
		if path:GetAge() > 0.1 then
			path:Compute(self, self:GetEnemy():GetPos())
		end

		path:Update(self)

		if options.draw then
			path:Draw()
		end

		if self.loco:IsStuck() then
			self:HandleStuck()
			return "stuck"
		end

		if math.random(1, 40) == 1 then
			self:PlayNextbotSound(CHASE_SOUNDS)
		end

		coroutine.yield()
	end

	return "ok"
end

function ENT:RunBehaviour()
	while true do
		if self:HaveEnemy() then
			local enemy = self:GetEnemy()
			if IsValid(enemy) then
				self.loco:FaceTowards(enemy:GetPos())
			end

			self:PlayNextbotSound(CHASE_SOUNDS)
			self:StartActivity(ACT_RUN)
			self.loco:SetDesiredSpeed(self.RunSpeed)
			self.loco:SetAcceleration(1200)
			self:ChaseEnemy()
			self.loco:SetAcceleration(400)
			self:StartActivity(ACT_IDLE)
		else
			self:PlayNextbotSound(IDLE_SOUNDS)
			self:StartActivity(ACT_WALK)
			self.loco:SetDesiredSpeed(self.WalkSpeed)
			self:MoveToPos(self:GetPos() + Vector(math.Rand(-1, 1), math.Rand(-1, 1), 0) * 500)
			self:StartActivity(ACT_IDLE)
		end

		coroutine.wait(0.5)
	end
end

function ENT:OnKilled(dmginfo)
	self:EmitSound(JUMPSCARE_SOUND, 80, 90, 1, CHAN_VOICE)
	hook.Call("OnNPCKilled", GAMEMODE, self, dmginfo:GetAttacker(), dmginfo:GetInflictor())
	self:Remove()
end
