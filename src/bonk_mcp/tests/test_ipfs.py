#!/usr/bin/env python3
"""
Test script for the IPFS functionality in the token launcher tool.
This script will test the ability to prepare IPFS metadata for a token,
handling both image upload and metadata creation.
"""

import asyncio
import sys
import argparse
from typing import Optional, Dict, Tuple
from pprint import pprint

# Import the utility functions directly
from bonk_mcp.utils import prepare_ipfs


async def test_prepare_ipfs(
    image_url: str,
    name: str,
    symbol: str,
    description: str,
    twitter: str = "",
    telegram: str = "",
    website: str = ""
) -> Optional[Tuple[str, str]]:
    """
    Test preparing IPFS metadata including image upload and metadata creation

    Args:
        image_url: URL of an image to test with
        name: Token name
        symbol: Token symbol
        description: Token description
        twitter: Twitter handle/URL (optional)
        telegram: Telegram group URL (optional)
        website: Website URL (optional)

    Returns:
        Tuple of (image_url, metadata_uri) if successful, None if failed
    """
    print(f"Testing prepare_ipfs with URL: {image_url}")
    print(f"Token: {name} ({symbol})")

    # Call the unified prepare_ipfs function
    metadata_uri = await prepare_ipfs(
        name=name,
        symbol=symbol,
        description=description,
        twitter=twitter,
        telegram=telegram,
        website=website,
        image_url=image_url
    )

    if not metadata_uri:
        print("❌ Failed to prepare IPFS metadata")
        return None

    print(f"✅ Successfully prepared IPFS metadata")
    print(f"📋 Metadata URI: {metadata_uri}")
    return (image_url, metadata_uri)


async def run_test(image_url: str = "https://sapphire-working-koi-276.mypinata.cloud/ipfs/bafkreiayu3rjnfvtmaj3dp67g2pny3kx42vzoxdkgdokbcvhdqe3rel7ym",
                   name: str = "Test Token",
                   symbol: str = "TEST",
                   description: str = "A test token created to validate the IPFS functionality",
                   twitter: str = "https://twitter.com/bonktoken",
                   telegram: str = "https://t.me/bonktoken",
                   website: str = "https://bonk.fun"):
    """
    Run the IPFS test

    Args:
        image_url: URL of an image to test with (default is a valid Pinata URL)
        name: Token name for metadata
        symbol: Token symbol for metadata
        description: Token description for metadata
        twitter: Twitter handle/URL (optional)
        telegram: Telegram group URL (optional)
        website: Website URL (optional)
    """
    print("=" * 60)
    print("IPFS FUNCTIONALITY TEST")
    print("=" * 60)

    # Test prepare_ipfs
    result = await test_prepare_ipfs(
        image_url=image_url,
        name=name,
        symbol=symbol,
        description=description,
        twitter=twitter,
        telegram=telegram,
        website=website
    )

    if not result:
        print("\n❌ Test failed: Could not prepare IPFS metadata")
        return

    image_url, metadata_uri = result

    print("\n" + "=" * 60)
    print("✅ TEST COMPLETED")
    print("=" * 60)
    print(f"📋 Image URL: {image_url}")
    print(f"📋 Metadata URI: {metadata_uri}")
    print("=" * 60)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Test IPFS functionality for token launcher')
    parser.add_argument('--image', type=str,
                        default="https://sapphire-working-koi-276.mypinata.cloud/ipfs/bafkreiayu3rjnfvtmaj3dp67g2pny3kx42vzoxdkgdokbcvhdqe3rel7ym",
                        help='URL of an image to test with (default is a valid Pinata URL)')
    parser.add_argument('--name', type=str,
                        default="Test Token", help='Token name for metadata')
    parser.add_argument('--symbol', type=str, default="TEST",
                        help='Token symbol for metadata')
    parser.add_argument('--description', type=str,
                        default="A test token created to validate the IPFS functionality",
                        help='Token description for metadata')
    parser.add_argument('--twitter', type=str,
                        default="https://twitter.com/bonktoken", help='Twitter URL (optional)')
    parser.add_argument('--telegram', type=str,
                        default="https://t.me/bonktoken", help='Telegram URL (optional)')
    parser.add_argument('--website', type=str,
                        default="https://bonk.fun", help='Website URL (optional)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_test(
        image_url=args.image,
        name=args.name,
        symbol=args.symbol,
        description=args.description,
        twitter=args.twitter,
        telegram=args.telegram,
        website=args.website
    ))
