import asyncio
import calendar
import datetime
import io
import json
import math
import os
import random
import time
import unicodedata
from pathlib import Path

import aiohttp
import asyncpg
import discord
import humanize
import requests
from discord import DMChannel
from discord.ext import commands, tasks
from discord.ext.commands import (BucketType, MissingPermissions, command,
                                  cooldown, has_permissions, when_mentioned_or)
from dotenv import load_dotenv

import ext.helpers as helpers


async def create_db_pool():
    bot.con=await asyncpg.create_pool(database='<insert db name here>',user='<insert user here>',password='<insert pass here>')

def get_extensions():
    extensions = []   
    extensions.append("jishaku")

    for file in Path("cogs").glob("**/*.py"):
        if "!" in file.name or "DEV" in file.name:
            continue
        extensions.append(str(file).replace("/", ".").replace(".py", ""))
    return extensions


class HelpCommand(commands.HelpCommand):
    def get_ending_note(self):
        return 'Use {0}{1} [command] for more info on a command.'.format(
            self.clean_prefix, self.invoked_with)

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = f'[{command.name}|{aliases}]'
            if parent:
                fmt = f'{parent}, {fmt}'
            alias = fmt
        else:
            alias = command.name if not parent else f'{parent} {command.name}'
        return f'{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title='Pycord-Chan', color=discord.Color.blurple())
        description = self.context.bot.description
        if description:
            embed.description = description

        for cog_, cmds in mapping.items():
            name = 'Other Commands' if cog_ is None else cog_.qualified_name
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                value = '\u2002'.join(c.name for c in cmds)
                if cog_ and cog_.description:
                    value = '{0}\n{1}'.format(cog_.description, value)

                embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=self.get_ending_note())
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog_):
        embed = discord.Embed(title='{0.qualified_name} Commands'.format(cog_))
        if cog_.description:
            embed.description = cog_.description

        filtered = await self.filter_commands(cog_.get_commands(), sort=True)
        for command in filtered:
            embed.add_field(name=self.get_command_signature(command),
                            value=command.short_doc or '...', inline=False)

        embed.set_footer(text=self.get_ending_note())
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=group.qualified_name)
        if group.help:
            embed.description = group.help

        if isinstance(group, commands.Group):
            filtered = await self.filter_commands(group.commands, sort=True)
            for command in filtered:
                embed.add_field(name=self.get_command_signature(command),
                                value=command.short_doc or '...', inline=False)

        embed.set_footer(text=self.get_ending_note())
        await self.get_destination().send(embed=embed)

    send_command_help = send_group_help


bot = commands.Bot(command_prefix="p!", description='The bot build with and for pycord.',
                  case_insensitive=True, embed_color=discord.Color.blurple(),
                  help_command=HelpCommand(), activity=discord.Activity(type=discord.ActivityType.competing, name="What's dpy's Best Fork?"), status=discord.Status.online)


bot.default_owner = 571638000661037056


@bot.event
async def on_invite_create(invite):
    await bot.tracker.update_invite_cache(invite)


@bot.event
async def on_invite_delete(invite):
    await bot.tracker.remove_invite_cache(invite)

os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ['JISHAKU_RETAIN'] = "True"



init_data = helpers.storage(bot)

bot.helpers = helpers
bot.default_prefixes = ['p!']
bot.server_cache = {}
bot.pools = pools
bot.owner_id = 571638000661037056
bot.owner_ids = init_data['owners']
bot.blacklisted = init_data['blacklisted']
bot.disabled = init_data['disabled']
bot.active_cogs = init_data['cogs']
bot.server_cache = {}

async def prefix(bot_, message):
    return commands.when_mentioned_or(*(await helpers.prefix(bot_, message)))(
        bot_, message)

@bot.event
async def on_ready():
    print("{} is Ready and Online!".format(bot.user))

@bot.event
async def on_command_error(ctx, error):
    exception = error
    if hasattr(ctx.command, 'on_error'):
        pass
    error = getattr(error, 'original', error)


    if ctx.author.id in ctx.bot.owner_ids:
        if (isinstance(error, (
                commands.MissingAnyRole,
                commands.CheckFailure,
                commands.DisabledCommand, commands.CommandOnCooldown,
                commands.MissingPermissions, commands.MaxConcurrencyReached))):
            try:
                await ctx.reinvoke()
            except discord.ext.commands.CommandError as e:
                pass
            else:
                return


    if (isinstance(error, (
            commands.BadArgument, commands.MissingRequiredArgument,
            commands.NoPrivateMessage, commands.CheckFailure,
            commands.DisabledCommand, commands.CommandInvokeError,
            commands.TooManyArguments, commands.UserInputError,
            commands.NotOwner, commands.MissingPermissions,
            commands.BotMissingPermissions, commands.MaxConcurrencyReached,
            commands.CommandNotFound))):
        await helpers.log_command_error(ctx, exception, True)
        if not isinstance(error, commands.CommandNotFound):
            if await helpers.is_disabled(ctx):
                return  
        text = None
        if isinstance(error, commands.CheckFailure):
            if bot.disabled:
                text = 'The bot is currently disabled. It will be back soon.'
        if not isinstance(error, commands.CommandNotFound):
            embed = discord.Embed(title="Error", description=text or str(error),
                              color=discord.Color.red())
            embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
            owner = bot.get_user(ctx.bot.owner_ids[0])
            embed.set_footer(
                icon_url=bot.user.avatar_url,
                text=f'If you think this is a mistake please contact {owner}')
            await ctx.send(embed=embed)

    elif isinstance(error, commands.CommandOnCooldown):
        await helpers.log_command_error(ctx, exception, True)
        time2 = datetime.timedelta(seconds=math.ceil(error.retry_after))
        error = (f'You are on cooldown. Try again after {humanize.precisedelta(time2)}')
        embed = discord.Embed(title="Error", description=error,
                          color=discord.Color.red())
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        owner = bot.get_user(ctx.bot.owner_ids[0])
        embed.set_footer(
            icon_url=bot.user.avatar_url,
            text=f'If you think this is a mistake please contact {owner}')
        await ctx.send(embed=embed)

    else:
        try:
            raise error
            embed = discord.Embed(title='Oh no!', description=(
                'An error occurred. My developer has been notified of it, '
                'but if it continues to occur please DM '
                f'<@{ctx.bot.owner_ids[0]}>'), color=discord.Color.red())
            await ctx.send(embed=embed)
        except discord.errors.Forbidden:
            pass
        await helpers.log_command_error(ctx, exception, False)


bot.launch_time = datetime.datetime.utcnow()

@bot.command()
async def ping(ctx):
        loading = '<:thinkCat:853565931838242816>'
        ws_ping = f'{(bot.latency * 1000):.2f}ms ' \
                  f'({humanize.precisedelta(datetime.timedelta(seconds=bot.latency))})'
        embed = discord.Embed(title='PONG!  :ping_pong:', description=(
            f'**{loading} Websocket:** {ws_ping}\n** :repeat: Round-Trip:** Calculating...'), color=discord.Color.blurple())
        start = time.perf_counter()
        message = await ctx.send(embed=embed)
        end = time.perf_counter()
        await asyncio.sleep(0.5)
        trip = end - start
        rt_ping = f'{(trip * 1000):.2f}ms ({humanize.precisedelta(datetime.timedelta(seconds=trip))})'
        embed.description = (
            f'**{loading} Websocket:** {ws_ping}\n**'
            f':repeat: Round-Trip:** {rt_ping}.')
        await message.edit(embed=embed)
        await asyncio.sleep(0.5)
        start = time.perf_counter()
        await message.edit(embed=embed)


for ext in get_extensions():
    bot.load_extension(ext)
    
bot.loop.run_until_complete(create_db_pool())
bot.run(os.getenv("TOKEN"))
